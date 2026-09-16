import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import replay_residual_sanity_runner_v1 as r

class LoaderMetadataTests(unittest.TestCase):
    def make_dir(self):
        td = tempfile.TemporaryDirectory()
        d = Path(td.name)
        (d / "manifest.json").write_text("{}")
        (d / "provenance.json").write_text("{}")
        for i in r.p.DEV_INDICES:
            (d / f"packet_{i:02d}.json").write_text(json.dumps({"frozen_index": i}))
        return td, d

    def call_loader(self, d):
        manifest = [{} for _ in r.p.DEV_INDICES]
        with mock.patch.object(r.p, "development_manifest", return_value=manifest), mock.patch.object(r.p, "validate_episode_packet", return_value=None):
            return r._load_packets(d, Path("."), tokenizer=None)

    def test_exact_episode_files_plus_required_metadata_pass(self):
        td, d = self.make_dir()
        try:
            packets, manifest = self.call_loader(d)
            self.assertEqual([p["frozen_index"] for p in packets], list(r.p.DEV_INDICES))
            self.assertEqual(len(manifest), len(r.p.DEV_INDICES))
        finally: td.cleanup()

    def test_unexpected_json_sidecar_fails_closed(self):
        td, d = self.make_dir()
        try:
            (d / "extra.json").write_text("{}")
            with self.assertRaisesRegex(RuntimeError, "EPISODE_DIR_UNEXPECTED_JSON_SIDECAR"): self.call_loader(d)
        finally: td.cleanup()

    def test_missing_packet_fails_closed(self):
        td, d = self.make_dir()
        try:
            (d / "packet_17.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "EPISODE_SET_MUST_BE_EXACT_0_31"): self.call_loader(d)
        finally: td.cleanup()

    def test_out_of_range_packet_filename_fails_closed(self):
        td, d = self.make_dir()
        try:
            (d / "packet_32.json").write_text(json.dumps({"frozen_index": 32}))
            with self.assertRaisesRegex(RuntimeError, "EPISODE_DIR_UNEXPECTED_JSON_SIDECAR"): self.call_loader(d)
        finally: td.cleanup()

    def test_filename_index_mismatch_fails_closed(self):
        td, d = self.make_dir()
        try:
            (d / "packet_05.json").write_text(json.dumps({"frozen_index": 6}))
            with self.assertRaisesRegex(RuntimeError, "EPISODE_FILENAME_INDEX_MISMATCH"): self.call_loader(d)
        finally: td.cleanup()

    def test_missing_required_metadata_fails_closed(self):
        td, d = self.make_dir()
        try:
            (d / "provenance.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "EPISODE_DIR_MISSING_REQUIRED_METADATA"): self.call_loader(d)
        finally: td.cleanup()

if __name__ == "__main__": unittest.main()
