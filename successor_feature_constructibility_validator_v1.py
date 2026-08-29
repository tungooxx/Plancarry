"""CLI validator/packetizer for frozen SuccessorFeature constructibility inputs.

No model/environment execution exists here. Runtime-adapter attempt material must
first be sealed as an exact-16 manifest; the resulting digest is then supplied
back as an externally bound value for packetization and terminal summary.
"""
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


def _fixed_json_files(directory: Path, *, noun: str) -> list[Path]:
    expected = [directory / f"attempt_{i:02d}.json" for i in drv.FIXED_INDICES]
    if any(not p.is_file() for p in expected):
        raise drv.DriverContractError(f"{noun}_DIRECTORY_MISSING_FIXED_INDEX")
    extras = sorted(p.name for p in directory.glob("*.json") if p not in expected)
    if extras:
        raise drv.DriverContractError(f"{noun}_DIRECTORY_HAS_EXTRA_JSON")
    return expected


def preflight(root: Path) -> dict[str, object]:
    return drv.build_manifest(root)


def seal_materials(root: Path, material_dir: Path, output_path: Path) -> dict[str, object]:
    manifest = drv.build_manifest(root)
    material_paths = _fixed_json_files(material_dir, noun="MATERIAL")
    materials = [_load(p) for p in material_paths]
    if any(not isinstance(x, dict) for x in materials):
        raise drv.DriverContractError("ATTEMPT_MATERIAL_FILE_MUST_BE_OBJECT")
    seal = drv.build_attempt_material_manifest(materials, manifest)  # type: ignore[arg-type]
    _write_atomic(output_path, seal)
    return seal


def _load_and_validate_material_manifest(
    root: Path, material_manifest_path: Path, expected_material_manifest_sha256: str
) -> tuple[dict[str, object], dict[str, object]]:
    manifest = drv.build_manifest(root)
    obj = _load(material_manifest_path)
    if not isinstance(obj, dict):
        raise drv.DriverContractError("MATERIAL_MANIFEST_FILE_MUST_BE_OBJECT")
    validated = drv.validate_attempt_material_manifest(obj, manifest, expected_material_manifest_sha256)
    return manifest, validated


def build_packet(
    root: Path,
    material_path: Path,
    material_manifest_path: Path,
    expected_material_manifest_sha256: str,
    output_path: Path,
) -> dict[str, object]:
    manifest, material_manifest = _load_and_validate_material_manifest(
        root, material_manifest_path, expected_material_manifest_sha256
    )
    material = _load(material_path)
    if not isinstance(material, dict):
        raise drv.DriverContractError("ATTEMPT_MATERIAL_MUST_BE_OBJECT")
    packet = drv.build_attempt_packet(
        material, manifest, material_manifest, expected_material_manifest_sha256
    )
    _write_atomic(output_path, packet)
    return packet


def summarize(
    root: Path,
    packet_dir: Path,
    material_dir: Path,
    material_manifest_path: Path,
    expected_material_manifest_sha256: str,
    output_path: Path,
) -> dict[str, object]:
    manifest, material_manifest = _load_and_validate_material_manifest(
        root, material_manifest_path, expected_material_manifest_sha256
    )
    packet_paths = _fixed_json_files(packet_dir, noun="PACKET")
    material_paths = _fixed_json_files(material_dir, noun="MATERIAL")
    packets = [_load(p) for p in packet_paths]
    materials = [_load(p) for p in material_paths]
    if any(not isinstance(p, dict) for p in packets):
        raise drv.DriverContractError("PACKET_FILE_MUST_BE_OBJECT")
    if any(not isinstance(m, dict) for m in materials):
        raise drv.DriverContractError("ATTEMPT_MATERIAL_FILE_MUST_BE_OBJECT")
    summary = drv.terminal_summary(
        packets, materials, material_manifest, expected_material_manifest_sha256, manifest  # type: ignore[arg-type]
    )
    _write_atomic(output_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    p_seal = sub.add_parser("seal-materials")
    p_seal.add_argument("material_dir", type=Path)
    p_seal.add_argument("output", type=Path)
    p_build = sub.add_parser("build-packet")
    p_build.add_argument("material", type=Path)
    p_build.add_argument("material_manifest", type=Path)
    p_build.add_argument("expected_material_manifest_sha256")
    p_build.add_argument("output", type=Path)
    p_sum = sub.add_parser("summarize")
    p_sum.add_argument("packet_dir", type=Path)
    p_sum.add_argument("material_dir", type=Path)
    p_sum.add_argument("material_manifest", type=Path)
    p_sum.add_argument("expected_material_manifest_sha256")
    p_sum.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        value = preflight(args.root)
    elif args.command == "seal-materials":
        value = seal_materials(args.root, args.material_dir, args.output)
    elif args.command == "build-packet":
        value = build_packet(
            args.root, args.material, args.material_manifest,
            args.expected_material_manifest_sha256, args.output,
        )
    else:
        value = summarize(
            args.root, args.packet_dir, args.material_dir, args.material_manifest,
            args.expected_material_manifest_sha256, args.output,
        )
    print(drv.canonical_json_bytes(value).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
