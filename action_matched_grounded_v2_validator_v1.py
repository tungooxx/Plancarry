from __future__ import annotations
import json
from pathlib import Path
from typing import Any,Mapping
import action_matched_grounded_v2_phase_runner_v1 as phase
class ValidationError(RuntimeError): pass

def validate_development_payload(obj:Mapping[str,Any])->None:
    phase.select_development(obj,None)
    for flag in ('confirmation_accessed','reserve_accessed','valid_seen_accessed','valid_unseen_accessed'):
        if obj.get(flag) is not False: raise ValidationError(f'development split isolation:{flag}')
def validate_confirmation_payload(obj:Mapping[str,Any],seal:Mapping[str,Any],seal_sha:str)->None:
    phase.evaluate_confirmation(obj,seal,seal_sha)
def validate_file(path:str|Path,kind:str,seal_path:str|Path|None=None)->None:
    obj=json.loads(Path(path).read_text())
    if kind=='development': validate_development_payload(obj)
    elif kind=='confirmation':
        if seal_path is None: raise ValidationError('seal required')
        seal=json.loads(Path(seal_path).read_text()); validate_confirmation_payload(obj,seal,phase.canonical_sha(seal))
    else: raise ValidationError('unknown kind')
