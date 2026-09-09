import json
import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hybrid_engine.evaluation.evidence_receipt import build_receipt, sign_receipt


class TestNARECLI(unittest.TestCase):
    def test_cli_emits_three_layer_report(self):
        manifest = []
        metrics = []
        for i in range(12):
            scene = f"s{i:02d}"
            manifest.append({
                "scene_id": scene, "session_id": f"session-{i}", "contributor": f"p{i%2}",
                "source_path": f"{scene}.raw", "target_path": f"{scene}.jpg",
                "source_sha256": f"{i:064x}", "target_sha256": f"{i+100:064x}",
                "picture_style": "standard", "lighting": ["daylight", "tungsten", "mixed"][i % 3],
                "scene_type": ["portrait", "landscape", "indoor"][i % 3],
                "split": "evaluation",
            })
            metrics.append({"scene_id": scene, "raw_delta_e00": 10,
                            "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                            "registration": {"ecc_correlation": 0.9,
                                             "overlap_fraction": 0.99,
                                             "shift_x_px": 0, "shift_y_px": 0,
                                             "long_edge_px": 512},
                            "subgroups": {
                                name: {"baseline_delta_e00": 10,
                                       "candidate_delta_e00": 9}
                                for name in ("skin", "sky", "foliage", "neutral",
                                             "saturated", "shadow", "highlight")
                            }})
        controls = {"subgroups_passed": True, "controls_passed": True,
                    "provenance_passed": True}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (("manifest", manifest), ("metrics", metrics), ("controls", controls)):
                (root / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
            proc = subprocess.run([
                sys.executable, "-m", "hybrid_engine.evaluation.nare_cli",
                "--manifest", str(root / "manifest.json"), "--metrics", str(root / "metrics.json"),
                "--controls", str(root / "controls.json"), "--bootstrap", "200", "--seed", "0",
            ], capture_output=True, text=True, check=True)
        report = json.loads(proc.stdout)
        self.assertFalse(report["classification"]["ship_gate_passed"])
        self.assertEqual(report["classification"]["classification"], "Inconclusive")
        self.assertFalse(report["classification"]["checks"]["trusted_provenance"])
        self.assertEqual(report["paired"]["n_scenes"], 12)

    def test_cli_accepts_only_a_matching_signed_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
                        "subgroups": {name: {"baseline_delta_e00": 10,
                                               "candidate_delta_e00": 9}
                                      for name in ("skin", "sky", "foliage", "neutral",
                                                   "saturated", "shadow", "highlight")}}
                       for i in range(12)]
            controls = {"subgroups_passed": True, "controls_passed": True,
                        "provenance_passed": True}
            values = {"manifest": manifest, "metrics": metrics, "controls": controls}
            paths = {}
            for name, value in values.items():
                path = root / f"{name}.json"
                path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
                paths[name] = path
            private = Ed25519PrivateKey.generate()
            public_path = root / "public.key"
            public_path.write_text(base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii"), encoding="ascii")
            receipt = sign_receipt(build_receipt(
                paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
                command=["nare-evaluator"], run_id="nare-run-1",
                timestamp="2026-09-09T00:00:00Z",
                required_artifacts=("manifest", "metrics", "controls")), private, key_id="ci")
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            command = [
                sys.executable, "-m", "hybrid_engine.evaluation.nare_cli",
                "--manifest", str(paths["manifest"]), "--metrics", str(paths["metrics"]),
                "--controls", str(paths["controls"]), "--bootstrap", "100", "--seed", "0",
                "--receipt", str(receipt_path), "--receipt-public-key", str(public_path),
                "--git-sha", "a" * 40,
            ]
            # A mathematically valid receipt from an arbitrary key is not a
            # trusted runner result and must remain Inconclusive.
            proc = subprocess.run(command, capture_output=True, text=True, check=True)
            report = json.loads(proc.stdout)
            self.assertFalse(report["classification"]["ship_gate_passed"])
            self.assertEqual(report["classification"]["classification"], "Inconclusive")
            self.assertFalse(report["classification"]["checks"]["trusted_provenance"])

            trusted_env = os.environ.copy()
            trusted_env["HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256"] = hashlib.sha256(
                private.public_key().public_bytes_raw()).hexdigest()
            trusted_env["HNCS_TRUSTED_EVALUATOR_SHA256"] = "b" * 64
            proc = subprocess.run(command, capture_output=True, text=True,
                                  check=True, env=trusted_env)
            report = json.loads(proc.stdout)
            self.assertTrue(report["classification"]["ship_gate_passed"])
            self.assertEqual(report["classification"]["classification"], "Supported")


if __name__ == "__main__":
    unittest.main()
