#!/usr/bin/env python3
"""Deterministic single-game ALFWorld TextWorld runtime for PlanCarry.

Hidden TextWorld facts are requested only to verify replay/reset identity. They
are never exposed to the evaluated language model.
"""
from __future__ import annotations
import hashlib, json, os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

BOUND_DATA_ROOT = Path(os.environ.get('ALFWORLD_DATA', '/opt/gpu-lab/data/plancarry-alfworld'))
PERSISTENT_DATA_ROOT = Path(os.environ.get(
    'PLANCARRY_ALFWORLD_PERSISTENT_DATA',
    '/opt/gpu-lab/envs/plancarry-alfworld-data',
))


def ensure_alfworld_data_alias(
    bound_root: Path = BOUND_DATA_ROOT,
    persistent_root: Path = PERSISTENT_DATA_ROOT,
) -> Path:
    """Ensure the bound ALFWorld path resolves to the persistent official assets.

    A valid caller-provided ALFWORLD_DATA is never overridden.  When the bound
    root exists only as an empty/non-persistent placeholder after a GPU-lab
    restart, recreate it as a symlink to the persistent env-volume copy.  This
    preserves the externally bound path and preregistered candidate path strings.
    """
    bound_root = Path(bound_root)
    persistent_root = Path(persistent_root)
    if (bound_root / 'json_2.1.1').is_dir():
        return bound_root
    if not (persistent_root / 'json_2.1.1').is_dir():
        raise RuntimeError(
            f'ALFWorld assets unavailable at bound={bound_root} and persistent={persistent_root}'
        )
    if bound_root.is_symlink():
        bound_root.unlink()
    elif bound_root.exists():
        if not bound_root.is_dir() or any(bound_root.iterdir()):
            raise RuntimeError(f'Refusing to replace non-empty ALFWorld data path: {bound_root}')
        bound_root.rmdir()
    bound_root.parent.mkdir(parents=True, exist_ok=True)
    bound_root.symlink_to(persistent_root, target_is_directory=True)
    if not (bound_root / 'json_2.1.1').is_dir():
        raise RuntimeError(f'Failed to materialize ALFWorld data alias: {bound_root}')
    return bound_root


ACTIVE_DATA_ROOT = ensure_alfworld_data_alias()
os.environ['ALFWORLD_DATA'] = str(ACTIVE_DATA_ROOT)

import textworld
import textworld.gym
import textworld.envs.pddl.textgen as textworld_textgen
from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos
from textworld_py313_compat import install_evalsymbol_explicit_locals

install_evalsymbol_explicit_locals(textworld_textgen)

DATA_ROOT = ACTIVE_DATA_ROOT / 'json_2.1.1'

def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=False)

def game_files(split: str='valid_seen', task_prefix: str|None=None) -> list[str]:
    root=DATA_ROOT/split
    paths=sorted(str(p) for p in root.rglob('game.tw-pddl'))
    if task_prefix:
        paths=[p for p in paths if f'/{task_prefix}-' in p]
    return paths

def _facts(info: dict[str,Any]) -> list[str]:
    facts=info.get('facts')
    if facts is None: return []
    # Batch env returns list per batch item.
    if isinstance(facts,(list,tuple)) and len(facts)==1 and isinstance(facts[0],(list,tuple,set)):
        facts=facts[0]
    return sorted(str(x) for x in facts)

def _commands(info: dict[str,Any]) -> list[str]:
    x=info.get('admissible_commands',[])
    if isinstance(x,(list,tuple)) and len(x)==1 and isinstance(x[0],(list,tuple)):
        x=x[0]
    return list(x)

def state_hash(game_file: str, observation: str, info: dict[str,Any], score: float, done: bool) -> str:
    payload={
        'game_file':str(Path(game_file).absolute()),
        'observation':observation,
        'admissible_commands':sorted(_commands(info)),
        'facts':_facts(info),
        'score':float(score),
        'done':bool(done),
    }
    return hashlib.sha256(stable_json(payload).encode()).hexdigest()

@dataclass
class AlfActionRecord:
    command: str
    observation: str
    score: float
    done: bool
    won: bool
    state_hash: str
    admissible_commands: list[str]
    error: str|None=None

class AlfRuntime:
    def __init__(self, game_file: str, max_steps: int=50):
        self.game_file=str(Path(game_file).absolute())
        request=textworld.EnvInfos(won=True, admissible_commands=True, facts=True, extras=['gamefile'])
        wrappers=[AlfredDemangler(shuffle=False), AlfredInfos]
        env_id=textworld.gym.register_games([self.game_file], request, batch_size=1,
                                            asynchronous=False, max_episode_steps=max_steps,
                                            wrappers=wrappers)
        self.env=textworld.gym.make(env_id)
        obs,info=self.env.reset()
        self.observation=str(obs[0]); self.info=info; self.score=0.0; self.done=False
        self.step_count=0

    @property
    def admissible_commands(self)->list[str]: return _commands(self.info)
    @property
    def won(self)->bool:
        x=self.info.get('won',[False])
        if isinstance(x,(list,tuple)): return bool(x[0])
        return bool(x)
    def hash(self)->str: return state_hash(self.game_file,self.observation,self.info,self.score,self.done)
    def step(self, command: str)->AlfActionRecord:
        if command not in self.admissible_commands:
            return AlfActionRecord(command,self.observation,self.score,self.done,self.won,self.hash(),list(self.admissible_commands),f'INVALID_COMMAND: {command}')
        obs,scores,dones,info=self.env.step([command])
        self.observation=str(obs[0]); self.info=info; self.score=float(scores[0]); self.done=bool(dones[0]); self.step_count+=1
        return AlfActionRecord(command,self.observation,self.score,self.done,self.won,self.hash(),list(self.admissible_commands),None)
    def close(self):
        try:self.env.close()
        except Exception: pass

def replay(game_file: str, records: list[AlfActionRecord], max_steps: int=50)->AlfRuntime:
    rt=AlfRuntime(game_file,max_steps=max_steps)
    for rec in records:
        out=rt.step(rec.command)
        if out.error != rec.error:
            rt.close(); raise AssertionError(f'replay error mismatch {rec.command}: {out.error!r} != {rec.error!r}')
        if out.state_hash != rec.state_hash:
            rt.close(); raise AssertionError(f'replay state mismatch after {rec.command}: {out.state_hash} != {rec.state_hash}')
    return rt
