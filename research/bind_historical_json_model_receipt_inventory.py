#!/usr/bin/env python3
"""Bounded read-only inventory of historical model-call *declarations*.

Do NOT interpret the absence of positive counters as proof of no actual model
inference: a repository snapshot omits external/remote jobs and runtime
request-response receipts. Never authorizes G0/G1 or creates model calls.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

SCHEMA="plancarry.bind.historical-json-bounded-model-call-declarations.v1"
KEYS={
    "model_calls", "total_model_calls", "successful_model_calls",
    "source_model_calls", "llm_requests", "llm_responses",
    "response_id", "model_response_id", "completion_id",
    "request_id", "model_output",
}

def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def _walk(value,path=()):
    if isinstance(value,dict):
        for k,v in value.items():
            sub=path+(str(k),)
            if str(k).lower() in KEYS:
                yield sub,v
            if isinstance(v,(list,dict)):
                yield from _walk(v,sub)
    elif isinstance(value,list):
        for i,x in enumerate(value):
            if isinstance(x,(dict,list)):
                yield from _walk(x,path+(str(i),))

def inventory(root:Path)->dict:
    folder=root/"results"
    if not folder.is_dir():
        raise FileNotFoundError("Historical results directory unavailable")
    files=sorted(folder.rglob("*.json"))
    if not files:
        raise ValueError("No archived JSON source declarations found")
    entries=[]
    field_counts=Counter()
    positive_numeric=[]
    textual=[]
    invalid=[]
    for p in files:
        raw=p.read_bytes()
        ref=str(p.relative_to(root))
        entry={"relative_path":ref,"sha256":sha(raw),"bytes":len(raw),"parsed":False,"declarations":[]}
        try:
            record=json.loads(raw)
        except (json.JSONDecodeError,UnicodeError) as exc:
            entry["parse_error_class"]=type(exc).__name__
            invalid.append(ref)
            entries.append(entry)
            continue
        entry["parsed"]=True
        for path,value in _walk(record):
            name=path[-1].lower()
            field_counts[name]+=1
            declaration={"path":list(path),"type":type(value).__name__}
            # Never include potentially sensitive literal model output/request
            # bodies; log safe counters and synthetic labels only.
            if name.endswith("model_calls") or name in ("llm_requests","llm_responses"):
                if type(value) in (int,float):
                    declaration["numeric_value"]=value
                    if value>0:
                        positive_numeric.append({"file":ref,"path":list(path),"value":value})
                elif isinstance(value,str):
                    declaration["text_label"]=value[:100]
                    textual.append({"file":ref,"path":list(path),"label":value[:100]})
            entry["declarations"].append(declaration)
        entries.append(entry)
    report={
        "schema":SCHEMA,
        "source_scope":"One recovered historical repository snapshot under results/**/*.json; does not include full GPU Lab remote job logs, provider data, connected apps, other local checkouts or model API receipts.",
        "file_count":len(entries),
        "parsed_count":sum(e["parsed"] for e in entries),
        "invalid_json_count":len(invalid),
        "invalid_json_paths":invalid,
        "field_counter":dict(sorted(field_counts.items())),
        "positive_numeric_call_declarations":positive_numeric,
        "nonnumeric_call_labels":textual,
        "all_available_receipt_fields_have_zero_numeric_positive_values":not positive_numeric,
        "full_historical_model_request_response_ledger_attested":False,
        "all_original_790_games_never_model_consumed_attested":False,
        "model_owned_source_plans_attested":False,
        "G0_CERTIFIED":False,
        "G1_AUTHORIZED":False,
        "scientific_gate":"NOT_AUTHORIZED",
        "model_calls_performed_by_audit":0,
        "files":entries,
    }
    report["manifest_sha256"]=sha(canonical(entries).encode("utf-8"))
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--historical-snapshot-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    x=p.parse_args()
    result=inventory(x.historical_snapshot_root)
    x.output.parent.mkdir(parents=True,exist_ok=True)
    x.output.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n")
    print(canonical({k:result[k] for k in ("schema","file_count","parsed_count","invalid_json_count","field_counter","positive_numeric_call_declarations","nonnumeric_call_labels","manifest_sha256","scientific_gate")}))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
