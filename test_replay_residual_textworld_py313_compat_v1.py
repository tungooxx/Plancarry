#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path


def test_py313_regression_signature():
    if sys.version_info < (3,13):
        return {'skipped':True,'reason':'python<3.13'}
    def legacy(expr, variables):
        locals().update(variables)
        return eval(expr)
    try:
        legacy('r', {'r':'ROOM'})
    except NameError as exc:
        return {'passed':True,'exception':f'{type(exc).__name__}:{exc}'}
    raise AssertionError('CPython>=3.13 unexpectedly preserved locals().update eval visibility')


def test_explicit_eval_semantics():
    from replay_residual_textworld_py313_compat_v1 import install_textworld_py313_eval_compat
    from textworld.envs.pddl import textgen
    prov=install_textworld_py313_eval_compat()
    cases=[
        ('r', {'r':'ROOM'}, 'ROOM'),
        ('len(r)', {'r':'ROOM'}, 4),
        ("context['variables']['r']", {'r':'ROOM'}, 'ROOM'),
    ]
    for expr,variables,expected in cases:
        got=textgen.EvalSymbol(expr, {'variables':variables}).derive()[0].symbol
        assert got==expected,(expr,got,expected)
    assert install_textworld_py313_eval_compat()['installed'] is True
    return {'passed':True,'cases':len(cases),'provenance':prov}


def test_consumed_dev0_reset_only():
    from replay_residual_textworld_py313_compat_v1 import install_textworld_py313_eval_compat
    install_textworld_py313_eval_compat()
    packet=json.loads(Path('results/science/plancarry_replay_residual_sanity_packets_v2/packet_00.json').read_text())
    from alfworld_runtime import AlfRuntime, DATA_ROOT
    rt=AlfRuntime(str(DATA_ROOT/packet['game_path']), max_steps=12)
    try:
        assert rt.step_count==0
        obs=str(rt.observation)
        cmds=list(rt.admissible_commands)
        assert obs and cmds
        return {
            'passed':True,
            'frozen_index':0,
            'step_count':rt.step_count,
            'observation_length':len(obs),
            'observation_sha256':hashlib.sha256(obs.encode()).hexdigest(),
            'admissible_command_count':len(cmds),
            'admissible_commands_sha256':hashlib.sha256(json.dumps(sorted(cmds),separators=(',',':')).encode()).hexdigest(),
            'model_calls':0,
            'actions_executed':0,
        }
    finally:
        rt.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--smoke-reset',action='store_true')
    args=ap.parse_args()
    out={
        'python':sys.version,
        'regression_signature':test_py313_regression_signature(),
        'explicit_eval_semantics':test_explicit_eval_semantics(),
    }
    if args.smoke_reset:
        out['consumed_dev0_reset_only']=test_consumed_dev0_reset_only()
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__':
    main()
