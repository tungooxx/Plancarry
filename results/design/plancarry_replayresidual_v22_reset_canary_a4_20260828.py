#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.metadata as md, json, os, shutil, sys, tempfile
from pathlib import Path

def sha256_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--expected-device-name', default='NVIDIA GeForce RTX 3080')
    ap.add_argument('--instance-id', default='vast_48954592')
    ns=ap.parse_args()
    root=Path(ns.root).resolve(); out=Path(ns.output).resolve()
    sys.path.insert(0,str(root))
    from replay_residual_textworld_py313_compat_v1 import install_textworld_py313_eval_compat
    shim_path=root/'replay_residual_textworld_py313_compat_v1.py'
    assert sha256_file(shim_path)=='a08a1e1e5536afc11d94868de40eaea89cb929ef43b59a1102f378446284a7f4'
    shim=install_textworld_py313_eval_compat()
    assert shim.get('installed') is True, shim
    import textworld
    tmp_root=Path(os.environ.get('TMPDIR','/tmp')).resolve()
    tmp_root.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='rr-v22-reset-canary-',dir=tmp_root))
    oldcwd=Path.cwd()
    try:
        os.chdir(work)
        opts=textworld.GameOptions(); opts.nb_rooms=1; opts.nb_objects=1; opts.quest_length=1; opts.seeds=20260828
        game_path,_=textworld.make(opts)
        env=textworld.start(game_path,request_infos=textworld.EnvInfos(admissible_commands=True))
        try:
            state=env.reset()
            obs_nonempty=bool(str(state).strip())
            adm_nonempty=bool(getattr(state,'admissible_commands',[]))
        finally:
            env.close()
    finally:
        os.chdir(oldcwd); shutil.rmtree(work,ignore_errors=True)
    assert obs_nonempty and adm_nonempty
    versions={x:md.version(x) for x in ['torch','transformers','tokenizers','textworld','alfworld']}
    assert sys.version_info[:3]==(3,13,15),sys.version
    assert versions=={'torch':'2.13.0','transformers':'4.51.3','tokenizers':'0.21.1','textworld':'1.7.0','alfworld':'0.4.2'},versions
    rec={
      'kind':'REPLAYRESIDUAL_V22_RESET_COMPATIBILITY_CANARY',
      'technical_status':'PASS',
      'target_kind':'SYNTHETIC_TEXTWORLD_GRAMMAR_CANARY',
      'attestation_contract_sha256':'40ae9747f675dc136a59ecc6e2c7ae28d4d329860566c542cbf1691d84bbc666',
      'compat_shim_sha256':'a08a1e1e5536afc11d94868de40eaea89cb929ef43b59a1102f378446284a7f4',
      'compat_shim_installed':True,
      'instance_id':ns.instance_id,
      'expected_device_name':ns.expected_device_name,
      'python':'.'.join(map(str,sys.version_info[:3])),
      'packages':versions,
      'study_cohort_access':False,
      'future_split_access':False,
      'alfworld_study_game_opened':False,
      'model_calls':0,'model_loads':0,'model_forwards':0,'model_generations':0,'environment_actions':0,
      'environment_reset':True,'initial_observation_nonempty':True,'admissible_commands_nonempty':True,
      'scientific_result':'NOT_ASSESSED_PRE_SCIENCE_CANARY_ONLY'
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(rec,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps(rec,sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
