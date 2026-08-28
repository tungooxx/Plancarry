#!/usr/bin/env python3
"""Host-only RTX 3080 adapter for registered ReplayResidual V2.2 packet execution.

This wrapper changes exactly one runtime guard in process memory: the frozen V2.1
producer's expected CUDA device name.  It delegates registration identity,
packet production, validation, attestation, population, controls, metrics, and
all scientific semantics to the independently reviewed V2.2 registered adapter.
"""
from __future__ import annotations

from typing import Sequence

import replay_residual_natural_packet_producer_v2_1 as frozen
import plancarry_replayresidual_v22_registered_packet_adapter_20260828 as registered

VAST_INSTANCE_ID = "vast_48954592"
SOURCE_DEVICE_NAME = "NVIDIA GeForce RTX 3050 Laptop GPU"
VAST_DEVICE_NAME = "NVIDIA GeForce RTX 3080"


def install_host_binding() -> None:
    """Install only the prospectively reviewed process-local device-name guard."""
    if frozen.EXPECTED_DEVICE_NAME not in {SOURCE_DEVICE_NAME, VAST_DEVICE_NAME}:
        raise RuntimeError(
            f"UNEXPECTED_PREEXISTING_DEVICE_BINDING:{frozen.EXPECTED_DEVICE_NAME!r}"
        )
    frozen.EXPECTED_DEVICE_NAME = VAST_DEVICE_NAME


def main(argv: Sequence[str] | None = None) -> int:
    install_host_binding()
    return int(registered.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
