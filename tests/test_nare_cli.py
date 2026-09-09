import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hybrid_engine.evaluation.evidence_receipt import build_receipt, sign_receipt


class TestNARECLI(unittest.TestCase):
    def _data(self):
        manifest = [{"scene_id": f"s{i}", "session_id": f"session-{i}",
                     "contributor": "p1", "source_path": f"s{i}.raw",
                     "target_path": f"s{i}.jpg", "source_sha256": f"{i:064x}",
                     "target_sha256": f"{i + 100:064x}", "picture_style": "standard",
                     "lighting": ["daylight", "tungsten", "mixed"][i % 3],
                     "scene_type": ["portrait", "landscape", "indoor"][i % 3],
                     "split": "evaluation"} for i in range(12)]
        metrics = [{"scene_id": f"s{i}", "raw_delta_e00": 10,
                    "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                    "registration": {"ecc_correlation": .9, "overlap_fraction": .99,
                                     "shift_x_px": 0, "shift_y_px": 0, "long_edge_px": 512},
                    "subgroups": {name: {"baseline_delta_e00": 10, "candidate_delta_e00": 9}
                                  for name in ("skin", "sky", "foliage", "neutral",
                                               "saturated", "shadow", "highlight")}}
                   for i in range(12)]
        controls = {"subgroups_passed": True, "controls_passed": True,
                    "provenance_passed": True}
        return manifest, metrics, controls

    def test_cli_emits_three_layer_report(self):
        manifest, metrics, controls = self._data()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (("manifest", manifest), ("metrics", metrics), ("controls", controls)):
                (root / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "hybrid_engine.evaluation.nare_cli",
                "--manifest", str(root / "manifest.json"), "--metrics", str(root / "metrics.json"),
                "--controls", str(root / "controls.json"), "--bootstrap", "200", "--seed", "0"],
                capture_output=True, text=True, check=True)
        report = json.loads(proc.stdout)
        self.assertFalse(report["classification"]["ship_gate_passed"])
        self.assertEqual(report["classification"]["classification"], "Inconclusive")
        self.assertFalse(report["classification"]["checks"]["receipt_integrity"])
        self.assertEqual(report["paired"]["bootstrap_draws"], 200)
        self.assertEqual(report["paired"]["bootstrap_seed"], 0)

    def test_valid_receipt_supports_nare_without_claiming_trusted_signer(self):
        manifest, metrics, controls = self._data()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for name, value in {"manifest": manifest, "metrics": metrics, "controls": controls}.items():
                path = root / f"{name}.json"
                path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
                paths[name] = path
            private = Ed25519PrivateKey.generate()
            public_path = root / "public.key"
            public_path.write_text(base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii"), encoding="ascii")
            receipt = sign_receipt(build_receipt(
                paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
                command=["nare-evaluator"], run_id="nare-run-1", timestamp="2026-09-09T00:00:00Z",
                run_config={"bootstrap": 100, "seed": 0},
                required_artifacts=("manifest", "metrics", "controls")), private, key_id="local")
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            command = [sys.executable, "-m", "hybrid_engine.evaluation.nare_cli",
                "--manifest", str(paths["manifest"]), "--metrics", str(paths["metrics"]),
                "--controls", str(paths["controls"]), "--bootstrap", "100", "--seed", "0",
                "--receipt", str(receipt_path), "--receipt-public-key", str(public_path),
                "--git-sha", "a" * 40]
            proc = subprocess.run(command, capture_output=True, text=True, check=True)
            report = json.loads(proc.stdout)
            self.assertTrue(report["classification"]["ship_gate_passed"])
            self.assertEqual(report["classification"]["classification"], "Supported")
            self.assertTrue(report["classification"]["checks"]["receipt_integrity"])
            self.assertFalse(report["paired"]["trusted_provenance"])
            self.assertTrue(report["evidence_receipt"]["signature_valid"])
            self.assertFalse(report["evidence_receipt"]["trusted"])
            mismatched = list(command)
            mismatched[mismatched.index("100")] = "101"
            failed = subprocess.run(mismatched, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("run_config", failed.stderr)


if __name__ == "__main__":
    unittest.main()
