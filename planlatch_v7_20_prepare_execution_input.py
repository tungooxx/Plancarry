from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

import planlatch_v7_20_controls as ctl
import planlatch_v7_20_runner as core
import planlatch_v7_20_execution_driver as driver
import planlatch_v7_9_train_manifest_builder as b

HERE=Path(__file__).resolve().parent
UNIVERSE=HERE/'results/design/planlatch_v7_20_universe_bodyblind_v2/source_manifest.json'
MEMBERSHIP=HERE/'results/design/planlatch_v7_20_execution_fixed36_v1/membership_receipt.json'
OUTPUT=HERE/'results/design/planlatch_v7_20_train_input'
EXPECTED_UNIVERSE_HASH='2bbd5228e125a6e3aaf3a7b41b7f0c44f194323bc6ba84880253cfff91056d26'
EXPECTED_RECEIPT='816185dbb1d966057a56d2994afc678ead6acdf8571b56a02616f240fc92a734'

def sha_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):
            h.update(c)
    return h.hexdigest()

def write_json(path:Path,obj:Any)->str:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=True)+'\n')
    return sha_file(path)

def partition_slot(index:int)->tuple[str,int]:
    if index<12:return 'FIT',index
    if index<20:return 'PILOT',index-12
    if index<32:return 'SUPPORT',index-20
    return 'CROSS_REALIZATION',index-32

def audit_exact(identity:str, expected_hash:str)->dict[str,Any]:
    parts=Path(identity).parts
    if len(parts)!=4 or parts[0]!='train' or parts[3]!='game.tw-pddl':
        raise RuntimeError(f'bad canonical identity {identity}')
    family,trial=parts[1],parts[2]
    family_path=b.TRAIN_ROOT/family
    exact_game=family_path/trial/'game.tw-pddl'
    if not exact_game.is_file():
        raise RuntimeError(f'missing exact TRAIN body {exact_game}')
    if sha_file(exact_game)!=expected_hash:
        raise RuntimeError(f'exact body hash mismatch {identity}')
    old=b.choose_trial
    try:
        b.choose_trial=lambda f: exact_game if f.resolve()==family_path.resolve() else old(f)
        row=b.audit_family(family_path)
    finally:
        b.choose_trial=old
    if row.get('eligible') is not True:
        raise RuntimeError(f'selected exact body not constructible: {identity}: {row}')
    if row.get('game_path')!=identity:
        raise RuntimeError(f'audit selected wrong body: {identity} -> {row.get("game_path")}')
    if row.get('game_sha256')!=expected_hash:
        raise RuntimeError(f'audit body sha mismatch: {identity}')
    return row

def main()->int:
    if OUTPUT.exists():
        raise RuntimeError(f'output must be fresh: {OUTPUT}')
    universe_rows=json.loads(UNIVERSE.read_text())
    receipt=json.loads(MEMBERSHIP.read_text())
    if receipt.get('receipt_sha256')!=EXPECTED_RECEIPT:
        raise RuntimeError('membership receipt mismatch')
    candidates=[ctl.UniverseCandidate(r['canonical_identity'],r['exact_body_sha256'],()) for r in universe_rows]
    ur=ctl.build_universe_receipt(candidates)
    if ur.ordered_universe_hash!=EXPECTED_UNIVERSE_HASH:
        raise RuntimeError(f'universe mismatch {ur.ordered_universe_hash}')
    byid={r['canonical_identity']:r for r in universe_rows}
    selected=receipt['selected_identities']
    if len(selected)!=36 or len(set(selected))!=36:
        raise RuntimeError('selected membership must be unique exact36')
    precomputed_path=HERE/"results/design/planlatch_v7_20_execution_fixed36_v1/precomputed_selected_rows.json"
    precomputed=json.loads(precomputed_path.read_text())
    if precomputed.get("membership_receipt_sha256")!=EXPECTED_RECEIPT:
        raise RuntimeError("precomputed-row receipt mismatch")
    rows=list(precomputed.get("rows") or [])
    if len(rows)!=36:
        raise RuntimeError("precomputed rows must be exact36")
    if [r.get("game_path") for r in rows]!=selected:
        raise RuntimeError("precomputed row identity order mismatch")
    for identity,row in zip(selected,rows):
        if row.get("game_sha256")!=byid[identity]["exact_body_sha256"]:
            raise RuntimeError(f"precomputed exact-body hash mismatch: {identity}")


    tasks=[]
    task_rows=[]
    block_to_row={}
    for i,row in enumerate(rows):
        part,slot=partition_slot(i)
        if receipt['partition_by_identity'].get(selected[i])!=part:
            raise RuntimeError('partition receipt mismatch')
        m0,_=b.m0_for(row)
        handle=f'v720-{part.lower()}-slot-{slot:02d}'
        rbit=slot%2
        pid=ctl.CANONICAL_PRODUCERS['R']
        coord=ctl.CanonicalCoordinate('R',rbit,pid,ctl.sha256_json({'producer_id':pid,'version':1}))
        t=core.BaseTaskMetadata(handle,m0,coord,part,'train')
        tasks.append(t)
        task_rows.append({
            'opaque_block_handle':handle,
            'm0':m0,
            'r':rbit,
            'r_producer_id':pid,
            'partition':part,
            'split':'train',
        })
        bid='opaque-B-'+ctl.sha256_json({'handle':handle})[:20]
        block_to_row[bid]=row

    frame=core.compile_pre_response_frame(tasks)
    core.verify_complete_cells(frame)
    if len(frame.block_ids)!=36 or len(frame.cells)!=576:
        raise RuntimeError('frame not exact 36x16')
    counts={p:list(frame.partition_by_block.values()).count(p) for p in ('FIT','PILOT','SUPPORT','CROSS_REALIZATION')}
    if counts!={'FIT':12,'PILOT':8,'SUPPORT':12,'CROSS_REALIZATION':4}:
        raise RuntimeError(counts)
    for part in counts:
        rs={t.r.value for t in tasks if t.partition==part}
        if rs!={0,1}:
            raise RuntimeError(f'R coverage failed {part}: {rs}')

    OUTPUT.mkdir(parents=True)
    partition_rows={p:[] for p in counts}
    orientations={'PILOT':{},'CROSS_REALIZATION':{}}
    for cell in frame.cells:
        row=block_to_row[cell.block_id]
        prompt,assigned=b.render_donor_prompt(row,cell.s,cell.sham,cell.a,cell.h)
        endpoints,orientation=b.opaque_endpoints(assigned)
        visible=b.reset_block(row)
        rec={'cell_id':cell.cell_id,'donor_prompt':prompt}
        if cell.partition=='FIT':
            rec.update({
                'actuator_visible_context':visible,
                'actuator_endpoints':endpoints,
                'actuator_orientation':orientation,
            })
        if cell.partition in ('PILOT','CROSS_REALIZATION'):
            rec.update({
                'relay_visible_context':visible,
                'relay_endpoints':endpoints,
                'valid_endpoint_ids':sorted(endpoints),
            })
            orientations[cell.partition][cell.cell_id]=orientation
        partition_rows[cell.partition].append(rec)

    partition_refs={}
    for part in ('FIT','PILOT','SUPPORT','CROSS_REALIZATION'):
        p=OUTPUT/f'{part}.json'
        partition_refs[part]={'path':p.relative_to(HERE).as_posix(),'sha256':write_json(p,{'partition':part,'records':partition_rows[part]})}
    orientation_refs={}
    for part in ('PILOT','CROSS_REALIZATION'):
        p=OUTPUT/f'{part}_orientation.json'
        orientation_refs[part]={'path':p.relative_to(HERE).as_posix(),'sha256':write_json(p,{'partition':part,'orientations':orientations[part]})}

    att={
        'mode':'DETERMINISTIC_FIXED36_PRE_OUTCOME_EXECUTION_SELECTION_V1',
        'candidate_universe_hash':EXPECTED_UNIVERSE_HASH,
        'membership_receipt_sha256':EXPECTED_RECEIPT,
        'membership_receipt_file_sha256':sha_file(MEMBERSHIP),
        'selected_count':36,
        'partition_counts':counts,
        'selection_seed_sha256':receipt['selection_seed_sha256'],
        'no_global_freshness_claim':True,
        'model_calls_before_input_freeze':0,
    }
    root={
        'kind':driver.ROOT_KIND,
        'experiment_id':driver.EXPERIMENT_ID,
        'tasks':task_rows,
        'partition_files':partition_refs,
        'orientation_files':orientation_refs,
        'universe_attestation':att,
        'donor_program_hash':b.DONOR_PROGRAM_HASH,
        'washout_hash':b.WASHOUT_HASH,
    }
    root_path=OUTPUT/'root.json'
    root_sha=write_json(root_path,root)

    loaded=driver.load_root_input(root_path)
    reframe=core.compile_pre_response_frame(loaded.tasks)
    core.verify_complete_cells(reframe)
    if reframe.frame_hash!=frame.frame_hash:
        raise RuntimeError('frame roundtrip mismatch')
    for part in ('FIT','PILOT','SUPPORT','CROSS_REALIZATION'):
        recs=driver._partition_records(loaded.partition_files[part],part)
        driver._verify_partition_coverage(reframe,part,recs)
    for part in ('PILOT','CROSS_REALIZATION'):
        orient=driver._orientation_rows(loaded.orientation_files[part],part)
        if set(orient)!={c.cell_id for c in reframe.cells if c.partition==part}:
            raise RuntimeError('orientation coverage mismatch')

    summary={
        'kind':'PLANLATCH_V720_EXECUTION_INPUT_MATERIALIZATION',
        'root_sha256':root_sha,
        'frame_hash':frame.frame_hash,
        'selected_count':36,
        'cell_count':576,
        'partition_counts':counts,
        'membership_receipt_sha256':EXPECTED_RECEIPT,
        'universe_hash':EXPECTED_UNIVERSE_HASH,
        'model_calls':0,
        'scientific_execution_performed':False,
    }
    write_json(OUTPUT/'materialization_summary.json',summary)
    print(json.dumps(summary,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
