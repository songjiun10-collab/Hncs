import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hybrid_engine.evaluation.evidence_receipt import (
    build_receipt,
    public_key_sha256,
    sign_receipt,
    validate_receipt,
)
from hybrid_engine.evaluation.eager_cli import build_report as eager_report


class TestEvidenceReceipt(unittest.TestCase):
    def _bundle(self, root):
        paths = {}
        for name, value in {
            "manifest": [{"scene_id": "s1", "split": "evaluation"}],
            "metrics": [{"scene_id": "s1", "candidate_delta_e00": 1}],
            "controls": {"identity_baseline": True},
            "robustness": {"daylight": True},
        }.items():
            path = root / f"{name}.json"
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
            paths[name] = path
        return paths

    def _signed(self, root):
        paths = self._bundle(root)
        private = Ed25519PrivateKey.generate()
        receipt = build_receipt(
            paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
            command=["python", "evaluate.py"], run_id="run-1",
            parent_run_id="dataset-1", timestamp="2026-09-09T00:00:00Z")
        signed = sign_receipt(receipt, private, key_id="ci-test")
        public_path = root / "public.key"
        public_path.write_text(base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii"), encoding="ascii")
        receipt_path = root / "receipt.json"
        receipt_path.write_text(json.dumps(signed, sort_keys=True), encoding="utf-8")
        return paths, receipt_path, public_path

    def test_signed_receipt_validates_integrity_without_claiming_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, receipt_path, public_path = self._signed(Path(directory))
            result = validate_receipt(receipt_path, paths, public_path)
            self.assertTrue(result["signature_valid"])
            self.assertFalse(result["trusted"])
            self.assertEqual(result["run_id"], "run-1")
            with self.assertRaisesRegex(ValueError, "git_sha"):
                validate_receipt(receipt_path, paths, public_path, expected_git_sha="c" * 40)

    def test_metric_mutation_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, receipt_path, public_path = self._signed(Path(directory))
            paths["metrics"].write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metrics"):
                validate_receipt(receipt_path, paths, public_path)

    def test_manifest_mutation_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, receipt_path, public_path = self._signed(Path(directory))
            paths["manifest"].write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest"):
                validate_receipt(receipt_path, paths, public_path)

    def test_expected_git_revision_is_bound_to_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, receipt_path, public_path = self._signed(Path(directory))
            with self.assertRaisesRegex(ValueError, "git_sha"):
                validate_receipt(receipt_path, paths, public_path,
                                 expected_git_sha="c" * 40)

    def test_run_configuration_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._bundle(root)
            private = Ed25519PrivateKey.generate()
            receipt = build_receipt(
                paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
                command=["evaluate"], run_id="run-config", timestamp="now",
                run_config={"bootstrap": 100, "seed": 0})
            signed = sign_receipt(receipt, private, key_id="ci-test")
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(signed), encoding="utf-8")
            public_path = root / "public.key"
            public_path.write_text(
                base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii"),
                encoding="ascii")
            with self.assertRaisesRegex(ValueError, "run_config"):
                validate_receipt(receipt_path, paths, public_path,
                                 expected_run_config={"bootstrap": 101, "seed": 0})

    def test_trusted_evaluator_fingerprint_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, receipt_path, public_path = self._signed(Path(directory))
            with self.assertRaisesRegex(ValueError, "evaluator"):
                validate_receipt(receipt_path, paths, public_path,
                                 trusted_evaluator_sha256="c" * 64)

    def test_unsigned_receipt_cannot_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._bundle(Path(directory))
            receipt = build_receipt(paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
                                    command=["evaluate"], run_id="run-1", timestamp="now")
            receipt_path = Path(directory) / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            public_path = Path(directory) / "public.key"
            public_path.write_text("not-a-key", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "signature"):
                validate_receipt(receipt_path, paths, public_path)

    def test_invalid_utf8_receipt_is_rejected_as_value_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt_path = root / "receipt.json"
            receipt_path.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                validate_receipt(receipt_path, {}, root / "missing.key")

    def test_eager_local_env_cannot_self_select_verified_trust(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = []
            metrics = []
            for index in range(12):
                scene = f"s{index}"
                manifest.append({"scene_id": scene, "source_body": "source", "target_body": "target",
                                 "illumination_id": "daylight", "source_path": f"{scene}.raw",
                                 "target_path": f"{scene}.jpg", "source_sha256": f"{index:064x}",
                                 "target_sha256": f"{index + 100:064x}", "split": "lockbox",
                                 "evidence_tier": "C"})
                metrics.append({"scene_id": scene, "baseline_delta_e00": 10., "candidate_delta_e00": 8.})
            values = {
                "manifest": manifest, "metrics": metrics,
                "controls": {name: True for name in ("identity_baseline", "target_reference_shuffle",
                    "source_label_shuffle", "holdout_rerun", "chart_positive_control")},
                "robustness": {"daylight": True},
            }
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
                command=["trusted-evaluator"], run_id="run-1", timestamp="2026-09-09T00:00:00Z",
                run_config={"bootstrap": 50, "seed": 0, "evidence_tier": "C",
                            "validation_passed": True, "lockbox_passed": True,
                            "external_replication": True}), private, key_id="ci")
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            attack_env = {"HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256": public_key_sha256(public_path),
                          "HNCS_TRUSTED_EVALUATOR_SHA256": "b" * 64}
            with patch.dict(os.environ, attack_env, clear=True):
                report = eager_report(
                    *(str(paths[name]) for name in ("manifest", "metrics", "controls", "robustness")),
                    "C", True, True, True, n_bootstrap=50,
                    receipt_path=str(receipt_path), receipt_public_key_path=str(public_path),
                    expected_git_sha="a" * 40)
            self.assertEqual(report["classification"]["classification"], "Supported")
            self.assertFalse(report["classification"]["checks"]["trusted_provenance"])
            self.assertTrue(report["evidence_receipt"]["signature_valid"])
            self.assertFalse(report["evidence_receipt"]["trusted"])
            with self.assertRaisesRegex(ValueError, "run_config"):
                eager_report(
                    *(str(paths[name]) for name in ("manifest", "metrics", "controls", "robustness")),
                    "C", True, False, True, n_bootstrap=50,
                    receipt_path=str(receipt_path), receipt_public_key_path=str(public_path),
                    expected_git_sha="a" * 40)


if __name__ == "__main__":
    unittest.main()
