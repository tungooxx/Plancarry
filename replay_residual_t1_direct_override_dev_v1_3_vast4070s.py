#!/usr/bin/env python3
"""Host-only RTX 4070 SUPER adapter for the frozen ReplayResidual T1 dev retry.

This wrapper changes only the producer's explicit device-name guard. It delegates
all scientific logic, OOM retry semantics, frozen population, model revision,
dtype, scoring, thresholds, and output contract to v1_2_oom_retry unchanged.
"""
from __future__ import annotations

import replay_residual_natural_packet_producer_v2_1 as p
import replay_residual_t1_direct_override_dev_v1_2_oom_retry as retry

VAST_DEVICE_NAME = "NVIDIA GeForce RTX 4070 SUPER"


def main() -> int:
    # Technical host migration only. The underlying frozen producer is not edited.
    p.EXPECTED_DEVICE_NAME = VAST_DEVICE_NAME
    return int(retry.main())


if __name__ == "__main__":
    raise SystemExit(main())
