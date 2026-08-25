#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Any,Mapping
import planunique_packet_builder_v1 as pb
import planunique_phase_runner_v1 as phase
class ValidationError(RuntimeError):pass
def validate_preflight(obj:Mapping[str,Any])->None:
 if obj.get('status')!='READY_NO_SCIENCE' or obj.get('model_calls')!=0 or obj.get('model_loads')!=0 or obj.get('environment_execution')!=0:raise ValidationError('PREFLIGHT_NOT_NO_SCIENCE')
 if obj.get('authority_commit')!=pb.AUTHORITY_COMMIT or obj.get('population_sha256')!=pb.POPULATION_SHA256:raise ValidationError('AUTHORITY_MISMATCH')
def validate_development_seal(obj:Mapping[str,Any])->None:
 if obj.get('status')!='FROZEN_PLANUNIQUE_DEVELOPMENT_SELECTION':raise ValidationError('NOT_FROZEN_SELECTION')
 if obj.get('authority_commit')!=pb.AUTHORITY_COMMIT or obj.get('population_sha256')!=pb.POPULATION_SHA256:raise ValidationError('SEAL_BINDING')
 e=obj.get('e_common_indices',[])
 if len(e)<24 or e!=sorted(set(e)) or not set(e).issubset(set(phase.DEV)):raise ValidationError('SEAL_E_COMMON')
 if int(obj.get('selected_layer',-1)) not in phase.LAYERS or float(obj.get('selected_alpha',-1)) not in phase.ALPHAS:raise ValidationError('SEAL_POINT')
def validate_confirmation_terminal(obj:Mapping[str,Any])->None:
 if int(obj.get('denominator',-1))!=20:raise ValidationError('CONFIRMATION_DENOMINATOR')
 if obj.get('status') not in {'SUPPORTED_PLANUNIQUE_T1','REFUTED_PLANUNIQUE_T1','INCONCLUSIVE_PLANUNIQUE_CONFIRMATION_QUALIFICATION'}:raise ValidationError('CONFIRMATION_STATUS')
