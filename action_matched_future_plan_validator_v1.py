from __future__ import annotations
import json
from pathlib import Path
from typing import Any,Mapping
import action_matched_future_plan_phase_runner_v1 as phase
class ValidationError(RuntimeError): pass
def validate_development_payload(obj:Mapping[str,Any])->None:
    phase.select_development(obj,None)
    if obj.get('confirmation_accessed') is not False or obj.get('reserve_accessed') is not False: raise ValidationError('development split isolation')
def validate_confirmation_payload(obj:Mapping[str,Any],seal:Mapping[str,Any],seal_sha:str)->None:
    phase.evaluate_confirmation(obj,seal,seal_sha)
def validate_file(path:str|Path,kind:str,seal_path:str|Path|None=None)->None:
    obj=json.loads(Path(path).read_text())
    if kind=='development': validate_development_payload(obj)
    elif kind=='confirmation':
        if seal_path is None: raise ValidationError('seal required')
        seal=json.loads(Path(seal_path).read_text()); validate_confirmation_payload(obj,seal,phase.canonical_sha(seal))
    else: raise ValidationError('unknown kind')
