#!/usr/bin/env python3
"""Output-rebound technical successor for frozen ReplayResidual V2.1 science.

Runtime compatibility is delegated unchanged to the independently reviewed
`replay_residual_natural_packet_producer_v2_1_py313_compat` wrapper.  This
module adds exactly one technical behavior: atomically publish the regenerated
packet set to the prospectively frozen V2.2 retry path rather than the invalid
V2.1 artifact path.

Packet schema and parent V2.1 scientific-contract provenance remain unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import replay_residual_natural_packet_producer_v2_1_py313_compat as compat

frozen = compat.frozen
SUCCESSOR_PACKET_TARGET_REL = Path(
    "results/science/plancarry_replay_residual_sanity_packets_v2_2_technical_retry1"
)
_ORIGINAL_ATOMIC_PUBLISH = frozen.atomic_publish_packet_set


def successor_atomic_publish_packet_set(
    root: Path,
    packets,
    final_rel: Path = frozen.FINAL_TARGET_REL,
    validator_fn=None,
    tokenizer=None,
):
    if Path(final_rel) != frozen.FINAL_TARGET_REL:
        raise RuntimeError(f"V22_UNEXPECTED_CALLER_FINAL_REL:{final_rel}")
    return _ORIGINAL_ATOMIC_PUBLISH(
        root,
        packets,
        final_rel=SUCCESSOR_PACKET_TARGET_REL,
        validator_fn=validator_fn,
        tokenizer=tokenizer,
    )


def main(argv: Sequence[str] | None = None) -> int:
    frozen.atomic_publish_packet_set = successor_atomic_publish_packet_set
    return compat.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
