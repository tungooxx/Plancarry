#!/usr/bin/env python3
from pathlib import Path
import hashlib
import torch
import replay_residual_t1_direct_override_causal_dev_v1_1 as d

EXPECTED='7c91979472a1346193710126fc641da6968cf39815df178ba69c66125983dd8a'
assert hashlib.sha256(Path('replay_residual_t1_direct_override_causal_dev_v1_1.py').read_bytes()).hexdigest()==EXPECTED
# Zero semantic controls are valid exact-zero controls under the frozen NONZERO norm-match rule.
z,ok=d.rescale_to(torch.zeros(8),3.0)
assert ok and torch.equal(z,torch.zeros(8))
# Nonzero controls are exact norm-matched within frozen tolerance.
x=torch.tensor([1.,2.,3.,4.]); y,ok=d.rescale_to(x,2.75)
assert ok and abs(float(torch.linalg.vector_norm(y))-2.75)<=2.75e-4
# Active-zero branch stays exactly zero and valid.
y0,ok0=d.rescale_to(x,0.0); assert ok0 and torch.equal(y0,torch.zeros_like(x))
# Random control is deterministic and norm-matched.
r1=d.rademacher_like(2048,4.25,'frozen-key'); r2=d.rademacher_like(2048,4.25,'frozen-key')
assert torch.equal(r1,r2) and abs(float(torch.linalg.vector_norm(r1))-4.25)<=4.25e-4
# Canonical reset snapshot definition is deterministic over the preregistered five invariants.
snap={'world_state_sha256':'a'*64,'current_observation':'obs','admissible_actions':['a','b'],'task_instruction':'task','reset_serialization':'reset'}
assert d.sha_json(snap)==d.sha_json(dict(reversed(list(snap.items()))))
# Direct runtime dependencies are fail-closed pinned before causal execution.
src=Path('replay_residual_t1_direct_override_causal_dev_v1_1.py').read_text()
for lit in [d.PRODUCER_SHA,d.SANITY_PROTOCOL_SHA,d.ALFWORLD_RUNTIME_SHA,d.TEXTWORLD_COMPAT_SHA,d.T1_PREREG_SHA,d.SESSION_SHA,d.PHASE_SHA]: assert lit in src
for forbidden in ['valid_seen/','valid_unseen/','packet_32.json','packet_52.json']: assert forbidden not in src
for required in ["'reset_snapshot_sha256'","'active_residual_sha256'","'injected_vector_sha256'","'selected_layer'","'selected_alpha'","'arm_name'","'session_id_hash'"]: assert required in src
print('PASS causal-dev-v1.2 deterministic contract tests')
