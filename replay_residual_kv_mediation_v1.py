"""Pre-science KV-cache splice utilities for ReplayResidual mediation.

Engineering-only module.  It contains no model/environment execution and no
ReplayResidual family access.  Cache sequence positions are never deleted or
reordered: every splice replaces values at fixed positions by concatenating a
PREFIX slice and a CYCLE slice along the existing sequence dimension (-2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

PLAN = "PLAN"
SEMANTIC_CONTROLS = (
    "NEXT_ACTION_PRESERVED_LATE_NULL",
    "UNRELATED_PLAN",
    "EQUAL_NORM_RANDOM",
)
ARM_A = "A_PERSIST"
ARM_B = "B_PREFIX_RESTORE"
ARM_C = "C_CYCLE_RESTORE"
ARM_D = "D_FULL_RESTORE"
ARM_E = "E_SHAM_SPLICE"
LOCALIZED_ARMS = (ARM_A, ARM_B, ARM_C)

Layer = Tuple[Any, Any]
ConcatFn = Callable[[Sequence[Any], int], Any]
DiffFn = Callable[[Any, Any], float]


class CacheContractError(ValueError):
    """Raised when a cache violates the frozen mediation geometry contract."""


@dataclass(frozen=True)
class CachePartition:
    prefix: Tuple[Layer, ...]
    cycle: Tuple[Layer, ...]
    prefix_len: int
    total_len: int


def _shape(tensor: Any) -> Tuple[int, ...]:
    try:
        return tuple(int(x) for x in tensor.shape)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        raise CacheContractError("cache tensor must expose an integer shape") from exc


def _meta(tensor: Any) -> Tuple[Any, Any]:
    return (getattr(tensor, "dtype", None), getattr(tensor, "device", None))


def _seq_len(tensor: Any) -> int:
    shape = _shape(tensor)
    if len(shape) < 2:
        raise CacheContractError(f"cache tensor rank must be >=2, got {shape}")
    return shape[-2]


def _slice_seq(tensor: Any, start: int, stop: int) -> Any:
    # Works for torch.Tensor and tensor-like synthetic fixtures.
    return tensor[..., start:stop, :]


def _default_concat(tensors: Sequence[Any], dim: int) -> Any:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only in real runtime
        raise RuntimeError("torch is required unless concat_fn is supplied") from exc
    return torch.cat(tuple(tensors), dim=dim)


def cache_layers(cache: Any) -> Tuple[Layer, ...]:
    """Return immutable layer pairs from legacy or DynamicCache-like storage."""
    if isinstance(cache, (tuple, list)):
        layers: List[Layer] = []
        for idx, pair in enumerate(cache):
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise CacheContractError(f"legacy layer {idx} is not a (key,value) pair")
            layers.append((pair[0], pair[1]))
        if not layers:
            raise CacheContractError("cache must contain at least one layer")
        return tuple(layers)

    if hasattr(cache, "key_cache") and hasattr(cache, "value_cache"):
        keys = list(cache.key_cache)
        values = list(cache.value_cache)
        if not keys or len(keys) != len(values):
            raise CacheContractError("DynamicCache-like key/value layer counts must match and be nonempty")
        return tuple(zip(keys, values))

    raise CacheContractError("unsupported cache representation")


def rebuild_like(template: Any, layers: Sequence[Layer]) -> Any:
    """Rebuild cache preserving legacy container or DynamicCache-like class."""
    layers = tuple(layers)
    if not layers:
        raise CacheContractError("cannot rebuild an empty cache")
    if isinstance(template, tuple):
        return tuple((k, v) for k, v in layers)
    if isinstance(template, list):
        return [(k, v) for k, v in layers]
    if hasattr(template, "key_cache") and hasattr(template, "value_cache"):
        try:
            rebuilt = type(template)()
        except Exception as exc:
            raise CacheContractError("DynamicCache-like class must be default-constructible") from exc
        rebuilt.key_cache = [k for k, _ in layers]
        rebuilt.value_cache = [v for _, v in layers]
        # Transformers DynamicCache versions may track this auxiliary field.
        if hasattr(rebuilt, "_seen_tokens"):
            try:
                rebuilt._seen_tokens = _seq_len(layers[0][0])
            except Exception:
                pass
        return rebuilt
    raise CacheContractError("unsupported cache template")


def validate_cache_geometry(cache: Any) -> Tuple[int, int]:
    layers = cache_layers(cache)
    total_len = None
    for idx, (key, value) in enumerate(layers):
        ks, vs = _shape(key), _shape(value)
        if len(ks) < 2 or len(vs) < 2:
            raise CacheContractError(f"layer {idx} cache rank must be >=2")
        if ks[-2] != vs[-2]:
            raise CacheContractError(f"layer {idx} key/value sequence lengths differ")
        if _meta(key) != _meta(value):
            raise CacheContractError(f"layer {idx} key/value dtype or device differs")
        if total_len is None:
            total_len = ks[-2]
        if ks[-2] != total_len:
            raise CacheContractError("all layers must share one total sequence length")
    assert total_len is not None
    return len(layers), int(total_len)


def validate_compatible_caches(left: Any, right: Any) -> Tuple[int, int]:
    ll = cache_layers(left)
    rr = cache_layers(right)
    if len(ll) != len(rr):
        raise CacheContractError("cache layer counts differ")
    _, total = validate_cache_geometry(left)
    _, total_r = validate_cache_geometry(right)
    if total != total_r:
        raise CacheContractError("cache total sequence lengths differ")
    for idx, ((lk, lv), (rk, rv)) in enumerate(zip(ll, rr)):
        for name, a, b in (("key", lk, rk), ("value", lv, rv)):
            if _shape(a) != _shape(b):
                raise CacheContractError(f"layer {idx} {name} shapes differ")
            if _meta(a) != _meta(b):
                raise CacheContractError(f"layer {idx} {name} dtype/device differs")
    return len(ll), total


def partition_cache(cache: Any, prefix_len: int) -> CachePartition:
    _, total_len = validate_cache_geometry(cache)
    if not isinstance(prefix_len, int) or not (0 < prefix_len < total_len):
        raise CacheContractError(f"prefix_len must satisfy 0 < prefix_len < {total_len}")
    prefix: List[Layer] = []
    cycle: List[Layer] = []
    for key, value in cache_layers(cache):
        prefix.append((_slice_seq(key, 0, prefix_len), _slice_seq(value, 0, prefix_len)))
        cycle.append((_slice_seq(key, prefix_len, total_len), _slice_seq(value, prefix_len, total_len)))
    return CachePartition(tuple(prefix), tuple(cycle), prefix_len, total_len)


def compose_cache(
    prefix_source: Any,
    cycle_source: Any,
    prefix_len: int,
    *,
    concat_fn: ConcatFn | None = None,
    template: Any | None = None,
) -> Any:
    """Splice prefix positions from one cache with cycle positions from another."""
    validate_compatible_caches(prefix_source, cycle_source)
    p = partition_cache(prefix_source, prefix_len)
    c = partition_cache(cycle_source, prefix_len)
    cat = concat_fn or _default_concat
    layers: List[Layer] = []
    for idx, ((pk, pv), (ck, cv)) in enumerate(zip(p.prefix, c.cycle)):
        key = cat((pk, ck), -2)
        value = cat((pv, cv), -2)
        if _seq_len(key) != p.total_len or _seq_len(value) != p.total_len:
            raise CacheContractError(f"layer {idx} splice changed token geometry")
        layers.append((key, value))
    return rebuild_like(prefix_source if template is None else template, layers)


def build_cache_arms(
    condition_cache: Any,
    clean_cache: Any,
    prefix_len: int,
    *,
    concat_fn: ConcatFn | None = None,
) -> Dict[str, Any]:
    """Build the exact preregistered A-E cache arms without mutation."""
    validate_compatible_caches(condition_cache, clean_cache)
    return {
        ARM_A: compose_cache(condition_cache, condition_cache, prefix_len, concat_fn=concat_fn, template=condition_cache),
        ARM_B: compose_cache(clean_cache, condition_cache, prefix_len, concat_fn=concat_fn, template=condition_cache),
        ARM_C: compose_cache(condition_cache, clean_cache, prefix_len, concat_fn=concat_fn, template=condition_cache),
        ARM_D: compose_cache(clean_cache, clean_cache, prefix_len, concat_fn=concat_fn, template=condition_cache),
        ARM_E: compose_cache(condition_cache, condition_cache, prefix_len, concat_fn=concat_fn, template=condition_cache),
    }


def cache_max_abs_diff(left: Any, right: Any, *, tensor_diff_fn: DiffFn | None = None) -> float:
    """Maximum elementwise absolute difference over all K/V layers."""
    validate_compatible_caches(left, right)
    if tensor_diff_fn is None:
        try:
            import torch  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("torch is required unless tensor_diff_fn is supplied") from exc

        def tensor_diff_fn(a: Any, b: Any) -> float:
            return float(torch.max(torch.abs(a - b)).detach().cpu().item())

    maximum = 0.0
    for (lk, lv), (rk, rv) in zip(cache_layers(left), cache_layers(right)):
        maximum = max(maximum, float(tensor_diff_fn(lk, rk)), float(tensor_diff_fn(lv, rv)))
    return maximum


def arm_matched_selective_contrasts(scores: Mapping[str, Any]) -> Dict[str, Any]:
    """Compute frozen arm-matched TOTAL/PROPAGATED/DIRECT contrasts.

    `scores[ARM_D]` must be one scalar clean baseline.  Each of A/B/C must be
    a mapping with PLAN and all three semantic controls.  Controls are never
    pooled across arms.
    """
    if ARM_D not in scores or isinstance(scores[ARM_D], Mapping):
        raise CacheContractError("D_FULL_RESTORE must be one scalar clean baseline")
    try:
        d = float(scores[ARM_D])
    except Exception as exc:
        raise CacheContractError("D_FULL_RESTORE must be numeric") from exc

    labels = {ARM_A: "TOTAL", ARM_B: "PROPAGATED", ARM_C: "DIRECT"}
    out: Dict[str, Any] = {"arm_deltas": {}}
    for arm, label in labels.items():
        table = scores.get(arm)
        if not isinstance(table, Mapping):
            raise CacheContractError(f"{arm} must be a condition->score mapping")
        required = (PLAN,) + SEMANTIC_CONTROLS
        missing = [name for name in required if name not in table]
        extra = [name for name in table if name not in required]
        if missing or extra:
            raise CacheContractError(f"{arm} requires exactly PLAN plus three controls; missing={missing}, extra={extra}")
        deltas = {name: float(table[name]) - d for name in required}
        max_control = max(deltas[name] for name in SEMANTIC_CONTROLS)
        selective = deltas[PLAN] - max_control
        out["arm_deltas"][arm] = deltas
        out[label] = selective
        out[f"{label}_max_control_delta"] = max_control
    return out


def identity_guard(
    condition_cache: Any,
    clean_cache: Any,
    arms: Mapping[str, Any],
    *,
    tensor_diff_fn: DiffFn | None = None,
) -> Dict[str, float]:
    """Engineering-only exact cache-content identity diagnostics."""
    required = (ARM_A, ARM_D, ARM_E)
    if any(name not in arms for name in required):
        raise CacheContractError("identity guard requires A, D, and E arms")
    return {
        "sham_E_vs_A_max_abs": cache_max_abs_diff(arms[ARM_E], arms[ARM_A], tensor_diff_fn=tensor_diff_fn),
        "persist_A_vs_condition_max_abs": cache_max_abs_diff(arms[ARM_A], condition_cache, tensor_diff_fn=tensor_diff_fn),
        "full_restore_D_vs_clean_max_abs": cache_max_abs_diff(arms[ARM_D], clean_cache, tensor_diff_fn=tensor_diff_fn),
    }
