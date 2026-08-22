#!/usr/bin/env python3
"""Install only the official assets required by ALFWorld TextWorld.

The stock alfworld-download also fetches a Mask R-CNN checkpoint. PlanCarry's
first ALFWorld benchmark uses AlfredTWEnv only, so this reproduces the official
JSON + TW-PDDL layout while intentionally omitting vision assets.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, tempfile, zipfile
from pathlib import Path
import requests
import alfworld.info as info

ASSETS = [
    ("json_2.1.1_json.zip", "https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_json.zip"),
    ("json_2.1.2_tw-pddl.zip", "https://github.com/alfworld/alfworld/releases/download/0.4.0/json_2.1.2_tw-pddl.zip"),
]

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def fetch(url: str, dst: Path) -> None:
    tmp=dst.with_suffix(dst.suffix+'.part')
    have=tmp.stat().st_size if tmp.exists() else 0
    headers={'Range':f'bytes={have}-'} if have else {}
    mode='ab' if have else 'wb'
    with requests.get(url,stream=True,headers=headers,timeout=60) as r:
        if have and r.status_code==200:
            have=0; mode='wb'
        r.raise_for_status()
        with tmp.open(mode) as f:
            for chunk in r.iter_content(1024*1024):
                if chunk: f.write(chunk)
    os.replace(tmp,dst)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-dir',required=True); args=ap.parse_args()
    root=Path(args.data_dir).resolve(); root.mkdir(parents=True,exist_ok=True)
    manifest={'data_dir':str(root),'assets':[],'vision_assets_downloaded':False}
    with tempfile.TemporaryDirectory(prefix='alfworld-text-') as td:
        td=Path(td)
        for name,url in ASSETS:
            archive=td/name
            print(f'DOWNLOAD {name}',flush=True); fetch(url,archive)
            digest=sha256(archive); size=archive.stat().st_size
            print(f'EXTRACT {name} size={size} sha256={digest}',flush=True)
            with zipfile.ZipFile(archive) as z: z.extractall(root)
            manifest['assets'].append({'name':name,'url':url,'bytes':size,'sha256':digest})
    logic=root/'logic'; logic.mkdir(exist_ok=True)
    shutil.copy2(info.ALFRED_PDDL_PATH,logic/'alfred.pddl')
    shutil.copy2(info.ALFRED_TWL2_PATH,logic/'alfred.twl2')
    manifest['logic']={'alfred.pddl':sha256(logic/'alfred.pddl'),'alfred.twl2':sha256(logic/'alfred.twl2')}
    counts={}
    base=root/'json_2.1.1'
    for split in ['train','valid_seen','valid_unseen']:
        p=base/split
        counts[split]={'traj_data':sum(1 for _ in p.rglob('traj_data.json')) if p.exists() else 0,
                       'tw_pddl':sum(1 for _ in p.rglob('game.tw-pddl')) if p.exists() else 0}
    manifest['counts']=counts
    (root/'plancarry_text_manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2),flush=True)
if __name__=='__main__': main()
