from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import torch
from torch import Tensor, nn

SCHEMA = "PLANCARRY_CPDS_V5_PREDICTIVE_RUNTIME_V1"
REALIZATION = "CPDS_PREDICTIVE_GRU256_BOUNDED_COSINE_V1"
BASE_MODEL_ID = "Qwen/Qwen3-1.7B"
BASE_MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
NATIVE_WIDTH = 2048
STATE_WIDTH = 256
G_GAIN = 1.0
ARMS = (
    "NO_CARRY", "STATIC_ONESHOT", "STATIC_REPEAT", "STATIC_PREDICTIVE_SHARED_G",
    "ALIGNED_RECURSION", "ZERO_Z0_RECURSION", "DONOR_Z0_RECURSION",
    "LAST_TRANSITION_ONLY", "BAGGED_TRANSITIONS", "TRANSITION_PERMUTED",
    "MATCHED_INFORMATION",
)


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_matrix(x: Tensor, width: int, name: str) -> Tensor:
    if x.ndim != 2 or x.shape[-1] != width:
        raise ValueError(f"{name}_SHAPE")
    if not torch.isfinite(x).all():
        raise ValueError(f"{name}_NONFINITE")
    return x.float()


def _require_vector(x: Tensor, width: int, name: str) -> Tensor:
    if x.ndim != 1 or x.shape[0] != width:
        raise ValueError(f"{name}_SHAPE")
    if not torch.isfinite(x).all():
        raise ValueError(f"{name}_NONFINITE")
    return x.float()


def unit_l2(x: Tensor, *, dim: int = -1) -> Tensor:
    if not torch.isfinite(x).all():
        raise ValueError("VECTOR_NONFINITE")
    ss = torch.sum(x.float() * x.float(), dim=dim, keepdim=True)
    if not torch.isfinite(ss).all() or torch.any(ss <= 0):
        raise ValueError("VECTOR_NORM")
    return x.float() / torch.sqrt(ss)


class CPDSV5Adapter(nn.Module):
    """Frozen-contract V5 F/G module. Base LLM features are inputs; base LLM weights are never members."""

    def __init__(self) -> None:
        super().__init__()
        # Construction order is scientifically frozen by the reviewed V5 contract.
        self.W0 = nn.Linear(NATIVE_WIDTH, STATE_WIDTH, bias=False)
        self.Wx = nn.Linear(NATIVE_WIDTH, STATE_WIDTH, bias=False)
        self.gru = nn.GRUCell(STATE_WIDTH, STATE_WIDTH)
        self.Wa = nn.Linear(NATIVE_WIDTH, STATE_WIDTH, bias=False)
        self.static_fc1 = nn.Linear(NATIVE_WIDTH, 512, bias=True)
        self.static_fc2 = nn.Linear(512, 512, bias=True)
        self.static_fc3 = nn.Linear(512, STATE_WIDTH, bias=True)

    def z0(self, h_pre_reset: Tensor) -> Tensor:
        h = _require_vector(h_pre_reset, NATIVE_WIDTH, "PRE_RESET")
        return unit_l2(self.W0(h))

    def static_state(self, h_pre_reset: Tensor) -> Tensor:
        h = _require_vector(h_pre_reset, NATIVE_WIDTH, "PRE_RESET")
        x = torch.tanh(self.static_fc1(h))
        x = torch.tanh(self.static_fc2(x))
        return unit_l2(self.static_fc3(x))

    def transition_input(self, h_transition: Tensor) -> Tensor:
        h = _require_vector(h_transition, NATIVE_WIDTH, "TRANSITION")
        return unit_l2(self.Wx(h))

    def step(self, z: Tensor, h_transition: Tensor) -> Tensor:
        z = _require_vector(z, STATE_WIDTH, "STATE")
        x = self.transition_input(h_transition)
        out = self.gru(x.unsqueeze(0), z.unsqueeze(0))[0]
        return unit_l2(out)

    def fold(self, z0: Tensor, transitions: Sequence[Tensor]) -> Tensor:
        z = unit_l2(_require_vector(z0, STATE_WIDTH, "STATE"))
        for h in transitions:
            z = self.step(z, h)
        return z

    def fold_zero_z0(self, transitions: Sequence[Tensor]) -> Tensor:
        if not transitions:
            raise ValueError("ZERO_Z0_REQUIRES_TRANSITION")
        z = torch.zeros(STATE_WIDTH, dtype=torch.float32, device=transitions[0].device)
        for h in transitions:
            z = self.step(z, h)
        return z

    def last_transition_only(self, z0: Tensor, transitions: Sequence[Tensor]) -> Tensor:
        z0u = unit_l2(_require_vector(z0, STATE_WIDTH, "STATE"))
        if not transitions:
            return z0u
        # No transition-to-transition state path: every transition is evaluated from z0.
        out = z0u
        for h in transitions:
            out = self.step(z0u, h)
        return out

    def bagged_transitions(self, z0: Tensor, transitions: Sequence[Tensor]) -> Tensor:
        z0u = unit_l2(_require_vector(z0, STATE_WIDTH, "STATE"))
        if not transitions:
            return z0u
        # Exact reviewed null: canonicalize the multiset before summation so floating-point
        # accumulation is bitwise invariant to the presented transition order. Each F call
        # remains independent from the same z0 and every transition is evaluated exactly once.
        keyed = []
        for h in transitions:
            hv = _require_vector(h, NATIVE_WIDTH, "TRANSITION")
            keyed.append((sha256_bytes(_tensor_bytes(hv)), hv))
        keyed.sort(key=lambda item: item[0])
        independent = [self.step(z0u, h) for _, h in keyed]
        return unit_l2(torch.stack(independent, dim=0).sum(dim=0))

    def action_q(self, h_actions: Tensor) -> Tensor:
        h = _require_matrix(h_actions, NATIVE_WIDTH, "ACTION")
        return unit_l2(self.Wa(h), dim=-1)

    def g_delta(self, z: Tensor, h_actions: Tensor) -> Tensor:
        z = unit_l2(_require_vector(z, STATE_WIDTH, "STATE"))
        q = self.action_q(h_actions)
        delta = torch.matmul(q, z) * G_GAIN
        if not torch.isfinite(delta).all():
            raise ValueError("G_NONFINITE")
        if torch.any(delta < -1.000001) or torch.any(delta > 1.000001):
            raise ValueError("G_OUT_OF_BOUNDS")
        return delta

    def adjusted_scores(self, base_scores: Tensor, z: Tensor, h_actions: Tensor) -> Tensor:
        if base_scores.ndim != 1 or not torch.isfinite(base_scores).all():
            raise ValueError("BASE_SCORES")
        if h_actions.ndim != 2 or h_actions.shape[0] != base_scores.shape[0]:
            raise ValueError("ACTION_SCORE_GEOMETRY")
        return base_scores.float() + self.g_delta(z, h_actions)

    def arm_state(
        self,
        arm: str,
        z0: Tensor,
        aligned_transitions: Sequence[Tensor],
        *,
        permuted_order: Sequence[int] | None = None,
        donor_transitions: Sequence[Tensor] | None = None,
        donor_z0: Tensor | None = None,
        h_pre_reset: Tensor | None = None,
    ) -> Tensor | None:
        if arm not in ARMS:
            raise ValueError("ARM")
        if arm == "NO_CARRY":
            return None
        if arm == "ZERO_Z0_RECURSION":
            # Strict null: do not inspect, normalize, or otherwise consume target z0.
            return self.fold_zero_z0(aligned_transitions)
        if arm == "STATIC_PREDICTIVE_SHARED_G":
            # Static null depends only on its own h_pre_reset encoder and shared Wa/G.
            if h_pre_reset is None:
                raise ValueError("STATIC_PRE_RESET_REQUIRED")
            return self.static_state(h_pre_reset)
        if arm == "DONOR_Z0_RECURSION":
            # Donor null replaces target z0 entirely; target z0 is not inspected.
            if donor_z0 is None:
                raise ValueError("DONOR_Z0_REQUIRED")
            donor = unit_l2(_require_vector(donor_z0, STATE_WIDTH, "DONOR_Z0"))
            return self.fold(donor, aligned_transitions)
        z0u = unit_l2(_require_vector(z0, STATE_WIDTH, "STATE"))
        if arm in ("STATIC_ONESHOT", "STATIC_REPEAT"):
            if arm == "STATIC_REPEAT":
                # Matched recurrent computation only; scratch has no path to exposed G state.
                _ = self.fold(z0u, aligned_transitions)
            return z0u
        if arm == "ALIGNED_RECURSION":
            return self.fold(z0u, aligned_transitions)
        if arm == "LAST_TRANSITION_ONLY":
            return self.last_transition_only(z0u, aligned_transitions)
        if arm == "BAGGED_TRANSITIONS":
            return self.bagged_transitions(z0u, aligned_transitions)
        if arm == "TRANSITION_PERMUTED":
            if permuted_order is None:
                raise ValueError("PERMUTATION_REQUIRED")
            order = tuple(int(i) for i in permuted_order)
            if sorted(order) != list(range(len(aligned_transitions))) or tuple(order) == tuple(range(len(order))):
                raise ValueError("PERMUTATION_NONIDENTITY")
            return self.fold(z0u, [aligned_transitions[i] for i in order])
        if arm == "MATCHED_INFORMATION":
            if donor_transitions is None or len(donor_transitions) != len(aligned_transitions):
                raise ValueError("DONOR_TRANSITIONS")
            return self.fold(z0u, donor_transitions)
        raise AssertionError


def deterministic_nonidentity_permutation(source_graph_id: str, n: int) -> tuple[int, ...]:
    if n < 2:
        raise ValueError("PERMUTATION_REQUIRES_AT_LEAST_TWO")
    digest = hashlib.sha256(("CPDS_V5_PERMUTE_V1\0" + source_graph_id).encode()).digest()
    shift = 1 + int.from_bytes(digest[:4], "big") % (n - 1)
    order = tuple((i + shift) % n for i in range(n))
    if order == tuple(range(n)):
        raise AssertionError("IDENTITY_PERMUTATION")
    return order


def _tensor_bytes(t: Tensor) -> bytes:
    x = t.detach().cpu().contiguous().float()
    # Header declares little-endian FLOAT32; byteswap only on big-endian hosts.
    import numpy as np
    a = x.numpy().astype("<f4", copy=False)
    return a.tobytes(order="C")


def save_deterministic_checkpoint(
    path: str | Path,
    model: CPDSV5Adapter,
    *,
    recipe_sha256: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    path = Path(path)
    entries = []
    payloads: list[bytes] = []
    for name, tensor in sorted(model.state_dict().items()):
        raw = _tensor_bytes(tensor)
        entries.append({"name": name, "shape": list(tensor.shape), "dtype": "FLOAT32_LE", "nbytes": len(raw), "sha256": sha256_bytes(raw)})
        payloads.append(raw)
    header = {
        "schema": "PLANCARRY_CPDS_V5_DETERMINISTIC_CHECKPOINT_V1",
        "realization": REALIZATION,
        "base_model_id": BASE_MODEL_ID,
        "base_model_revision": BASE_MODEL_REVISION,
        "recipe_sha256": recipe_sha256,
        "state": entries,
        "provenance": dict(provenance),
    }
    hb = canonical_bytes(header)
    blob = b"CPDSV5CKPT1\n" + struct.pack("<Q", len(hb)) + hb + b"".join(payloads)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return {"path": str(path), "sha256": sha256_bytes(blob), "bytes": len(blob), "header_sha256": sha256_bytes(hb), "header": header}


def load_deterministic_checkpoint(path: str | Path, model: CPDSV5Adapter, *, expected_sha256: str | None = None) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    if expected_sha256 is not None and sha256_bytes(raw) != expected_sha256:
        raise ValueError("CHECKPOINT_SHA")
    magic = b"CPDSV5CKPT1\n"
    if not raw.startswith(magic):
        raise ValueError("CHECKPOINT_MAGIC")
    off = len(magic)
    hlen = struct.unpack("<Q", raw[off:off+8])[0]; off += 8
    header = json.loads(raw[off:off+hlen]); off += hlen
    state = {}
    import numpy as np
    for e in header["state"]:
        n = int(e["nbytes"]); chunk = raw[off:off+n]; off += n
        if sha256_bytes(chunk) != e["sha256"]:
            raise ValueError("CHECKPOINT_TENSOR_SHA")
        a = np.frombuffer(chunk, dtype="<f4").copy().reshape(e["shape"])
        state[e["name"]] = torch.from_numpy(a)
    if off != len(raw):
        raise ValueError("CHECKPOINT_TRAILING_BYTES")
    model.load_state_dict(state, strict=True)
    return header


def canonical_action_payload(action: str) -> bytes:
    if not isinstance(action, str) or not action:
        raise ValueError("ACTION")
    return json.dumps({"action": action}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_transition_payload(command: str, observation: str) -> bytes:
    if not all(isinstance(x, str) and x for x in (command, observation)):
        raise ValueError("TRANSITION")
    return json.dumps({"command": command, "observation": observation}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load_frozen_qwen(cache_dir: str | Path, *, device: str = "cuda") -> tuple[Any, Any]:
    """Load only the exact frozen V5/V4 base checkpoint from local cache; never changes its weights."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if device == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA_REQUIRED")
        if not torch.cuda.is_bf16_supported():
            raise ValueError("CUDA_BF16_REQUIRED")
    tok = AutoTokenizer.from_pretrained(
        BASE_MODEL_ID, revision=BASE_MODEL_REVISION, cache_dir=str(cache_dir),
        local_files_only=True, use_fast=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID, revision=BASE_MODEL_REVISION, cache_dir=str(cache_dir),
        local_files_only=True, torch_dtype=torch.bfloat16, device_map=None,
    )
    model.to(device=torch.device(device), dtype=torch.bfloat16)
    model.eval(); model.requires_grad_(False)
    if next(model.parameters()).device.type != torch.device(device).type:
        raise ValueError("MODEL_DEVICE")
    return tok, model


def native_hidden_feature(model: Any, tokenizer: Any, payload_utf8: bytes) -> Tensor:
    """Exact isolated final-hidden extractor. Caller must load the frozen model/revision."""
    text = payload_utf8.decode("utf-8")
    ids = tokenizer(text, add_special_tokens=False, return_tensors=None)["input_ids"]
    if not ids:
        raise ValueError("EMPTY_TOKEN_SEQUENCE")
    device = next(model.parameters()).device
    x = torch.tensor([ids], dtype=torch.long, device=device)
    with torch.no_grad():
        h = model.model(input_ids=x, use_cache=False).last_hidden_state[0, -1].float().cpu()
    if h.shape != (NATIVE_WIDTH,):
        raise ValueError("NATIVE_WIDTH")
    return unit_l2(h)


def teacher_forced_whole_action_score(model: Any, tokenizer: Any, prompt: str, action: str) -> float:
    """Exact V4-compatible branch-blind whole-action score. No evaluator class labels are arguments."""
    if not isinstance(prompt, str) or not prompt or not isinstance(action, str) or not action:
        raise ValueError("SCORER_INPUT")
    suffix = " " + action
    pids = tokenizer(prompt, add_special_tokens=False, return_tensors=None)["input_ids"]
    fids = tokenizer(prompt + suffix, add_special_tokens=False, return_tensors=None)["input_ids"]
    if not pids or len(fids) <= len(pids) or fids[:len(pids)] != pids:
        raise ValueError("TOKENIZER_PREFIX_GUARD")
    device = next(model.parameters()).device
    ids = torch.tensor([fids], dtype=torch.long, device=device)
    with torch.no_grad():
        logits = model(input_ids=ids, use_cache=False).logits[0].double()
    total = 0.0
    for j, tok in enumerate(fids[len(pids):]):
        pos = len(pids) + j - 1
        lp = torch.log_softmax(logits[pos], dim=-1)[int(tok)]
        v = float(lp.item())
        if not math.isfinite(v):
            raise ValueError("SCORE_NONFINITE")
        total += v
    if not math.isfinite(total):
        raise ValueError("SCORE_NONFINITE")
    return total
