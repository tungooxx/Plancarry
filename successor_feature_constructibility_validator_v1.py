"""CLI validator/packetizer for frozen SuccessorFeature constructibility inputs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import successor_feature_constructibility_driver_v1 as drv


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = drv.canonical_json_bytes(value) + b"\n"
    fd, tmp = tempfile.mkstemp(prefix=".inprogress_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def preflight(root: Path) -> dict[str, object]:
    return drv.build_manifest(root)


def build_packet(root: Path, material_path: Path, output_path: Path) -> dict[str, object]:
    manifest = drv.build_manifest(root)
    material = _load(material_path)
    if not isinstance(material, dict):
        raise drv.DriverContractError("ATTEMPT_MATERIAL_MUST_BE_OBJECT")
    packet = drv.build_attempt_packet(material, manifest)
    _write_atomic(output_path, packet)
    return packet


def summarize(root: Path, packet_dir: Path, output_path: Path) -> dict[str, object]:
    manifest = drv.build_manifest(root)
    expected = [packet_dir / f"attempt_{i:02d}.json" for i in drv.FIXED_INDICES]
    if any(not p.is_file() for p in expected):
        raise drv.DriverContractError("PACKET_DIRECTORY_MISSING_FIXED_INDEX")
    extras = sorted(p.name for p in packet_dir.glob("*.json") if p not in expected)
    if extras:
        raise drv.DriverContractError("PACKET_DIRECTORY_HAS_EXTRA_JSON")
    packets = [_load(p) for p in expected]
    if any(not isinstance(p, dict) for p in packets):
        raise drv.DriverContractError("PACKET_FILE_MUST_BE_OBJECT")
    summary = drv.terminal_summary(packets, manifest)  # type: ignore[arg-type]
    _write_atomic(output_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    p_build = sub.add_parser("build-packet")
    p_build.add_argument("material", type=Path)
    p_build.add_argument("output", type=Path)
    p_sum = sub.add_parser("summarize")
    p_sum.add_argument("packet_dir", type=Path)
    p_sum.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        value = preflight(args.root)
    elif args.command == "build-packet":
        value = build_packet(args.root, args.material, args.output)
    else:
        value = summarize(args.root, args.packet_dir, args.output)
    print(drv.canonical_json_bytes(value).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
