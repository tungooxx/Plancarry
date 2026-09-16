#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Any,Mapping
import localcontinuation_packet_builder_v1 as pb
import localcontinuation_phase_runner_v1 as phase
class ValidationError(RuntimeError):pass

def validate_packet_set(obj:Mapping[str,Any],expected_phase:str,root:str|Path='.') -> None:
 rows=obj.get('packets',[]);expected=list(pb.PHASE_RANGES[expected_phase])
 if [int(x.get('frozen_index',-1)) for x in rows]!=expected:raise ValidationError('packet indices mismatch')
 for r in rows:pb.validate_reference_packet(r,expected_phase,root)
def validate_development_payload(obj:Mapping[str,Any])->None:
 if obj.get('phase')!='LOCALCONTINUATION_DEVELOPMENT':raise ValidationError('phase mismatch')
 phase.select_development(obj,None)
 if obj.get('confirmation_accessed') is not False or obj.get('reserve_accessed') is not False:raise ValidationError('development split isolation mismatch')
 ep=obj.get('execution_provenance')
 if not isinstance(ep,dict) or obj.get('execution_provenance_sha256')!=phase.sha_json(ep):raise ValidationError('development execution provenance mismatch')
def validate_confirmation_payload(obj:Mapping[str,Any],seal_sha256:str|None=None)->None:
 if obj.get('phase')!='LOCALCONTINUATION_CONFIRMATION':raise ValidationError('phase mismatch')
 phase._check_bindings(obj);phase._family_map(obj,phase.CONF); ep=obj.get('execution_provenance');
 if not isinstance(ep,dict) or obj.get('execution_provenance_sha256')!=phase.sha_json(ep):raise ValidationError('execution provenance missing or corrupt')
 if obj.get('reserve_accessed') is not False or obj.get('valid_seen_accessed') is not False or obj.get('valid_unseen_accessed') is not False:raise ValidationError('confirmation isolation violated')
 if obj.get('reserve_accessed') is not False or obj.get('valid_seen_accessed') is not False or obj.get('valid_unseen_accessed') is not False:raise ValidationError('confirmation split isolation mismatch')
 if seal_sha256 is not None and obj.get('development_seal_sha256')!=seal_sha256:raise ValidationError('seal hash mismatch')
def validate_replication_payload(obj:Mapping[str,Any],seal_sha256:str|None=None)->None:
 if obj.get('phase')!='LOCALCONTINUATION_REPLICATION':raise ValidationError('phase mismatch')
 phase._check_bindings(obj);phase._family_map(obj,phase.RESERVE); ep=obj.get('execution_provenance');
 if not isinstance(ep,dict) or obj.get('execution_provenance_sha256')!=phase.sha_json(ep):raise ValidationError('execution provenance missing or corrupt')
 if obj.get('valid_seen_accessed') is not False or obj.get('valid_unseen_accessed') is not False:raise ValidationError('replication isolation violated')
 if obj.get('valid_seen_accessed') is not False or obj.get('valid_unseen_accessed') is not False:raise ValidationError('replication split isolation mismatch')
 if seal_sha256 is not None and obj.get('development_seal_sha256')!=seal_sha256:raise ValidationError('seal hash mismatch')
def validate_file(path:str|Path,kind:str,seal_sha256:str|None=None)->None:
 obj=json.loads(Path(path).read_text())
 if kind=='development':validate_development_payload(obj)
 elif kind=='confirmation':validate_confirmation_payload(obj,seal_sha256)
 elif kind=='replication':validate_replication_payload(obj,seal_sha256)
 else:raise ValidationError('unknown kind')
