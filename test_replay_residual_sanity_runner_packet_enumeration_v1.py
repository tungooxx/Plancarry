from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import replay_residual_sanity_runner_v1 as r


class PacketEnumerationTests(unittest.TestCase):
    def _make_dir(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        td = tempfile.TemporaryDirectory()
        d = Path(td.name)
        (d / "manifest.json").write_text("{}", encoding="utf-8")
        (d / "provenance.json").write_text("{}", encoding="utf-8")
        for i in r.p.DEV_INDICES:
            (d / f"packet_{int(i):02d}.json").write_text(json.dumps({"frozen_index": int(i)}), encoding="utf-8")
        return td, d

    def _load(self, d: Path):
        manifest = [{"frozen_index": int(i)} for i in r.p.DEV_INDICES]
        with patch.object(r.p, "development_manifest", return_value=manifest), \
             patch.object(r.p, "validate_episode_packet", return_value=None):
            return r._load_packets(d, Path("/unused"), object())

    def test_valid_exact_directory_loads_32_packets_and_ignores_metadata_as_packets(self):
        td, d = self._make_dir()
        try:
            packets, manifest = self._load(d)
            self.assertEqual([p["frozen_index"] for p in packets], list(r.p.DEV_INDICES))
            self.assertEqual(len(packets), 32)
            self.assertEqual(len(manifest), 32)
        finally:
            td.cleanup()

    def test_manifest_is_not_interpreted_as_packet(self):
        td, d = self._make_dir()
        try:
            (d / "manifest.json").write_text(json.dumps({"frozen_index": -1}), encoding="utf-8")
            packets, _ = self._load(d)
            self.assertEqual(len(packets), 32)
        finally:
            td.cleanup()

    def test_missing_packet_fails_closed(self):
        td, d = self._make_dir()
        try:
            (d / "packet_31.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "EPISODE_SET_MUST_BE_EXACT_0_31"):
                self._load(d)
        finally:
            td.cleanup()

    def test_out_of_range_packet_index_fails_closed(self):
        td, d = self._make_dir()
        try:
            (d / "packet_00.json").write_text(json.dumps({"frozen_index": 99}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "EPISODE_FILENAME_INDEX_MISMATCH"):
                self._load(d)
        finally:
            td.cleanup()

    def test_filename_index_mismatch_fails_closed(self):
        td, d = self._make_dir()
        try:
            (d / "packet_01.json").write_text(json.dumps({"frozen_index": 0}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "EPISODE_FILENAME_INDEX_MISMATCH"):
                self._load(d)
        finally:
            td.cleanup()

    def test_unexpected_json_fails_closed(self):
        td, d = self._make_dir()
        try:
            (d / "junk.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "EPISODE_DIR_UNEXPECTED_JSON_SIDECAR"):
                self._load(d)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
