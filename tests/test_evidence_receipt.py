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
    sign_receipt,
    validate_receipt,
    public_key_sha256,
    receipt_signer_is_trusted,
    trusted_receipt_signers,
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
        public = private.public_key()
        receipt = build_receipt(
            paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
            command=["python", "evaluate.py"], run_id="run-1",
            parent_run_id="dataset-1", timestamp="2026-09-09T00:00:00Z",
        )
        signed = sign_receipt(receipt, private, key_id="ci-test")
        public_path = root / "public.key"
        public_path.write_text(base64.b64encode(
            public.public_bytes_raw()).decode("ascii"), encoding="ascii")
        receipt_path = root / "receipt.json"
        receipt_path.write_text(json.dumps(signed, sort_keys=True), encoding="utf-8")
        return paths, receipt_path, public_path

    def test_signed_receipt_validates_the_artifact_hash_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, receipt_path, public_path = self._signed(Path(directory))
            result = validate_receipt(receipt_path, paths, public_path)
            self.assertTrue(result["trusted"])
            self.assertEqual(result["run_id"], "run-1")
            self.assertEqual(result["evaluator_sha256"], "b" * 64)
            self.assertEqual(result["attestations"], {})
            with self.assertRaisesRegex(ValueError, "git_sha"):
                validate_receipt(receipt_path, paths, public_path, expected_git_sha="c" * 40)

    def test_metric_mutation_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, receipt_path, public_path = self._signed(Path(directory))
            paths["metrics"].write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metrics"):
                validate_receipt(receipt_path, paths, public_path)

    def test_unsigned_receipt_cannot_be_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._bundle(Path(directory))
            receipt = build_receipt(paths, git_sha="a" * 40,
                                    evaluator_sha256="b" * 64,
                                    command=["evaluate"], run_id="run-1",
                                    timestamp="2026-09-09T00:00:00Z")
            receipt_path = Path(directory) / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            public_path = Path(directory) / "public.key"
            public_path.write_text("not-a-key", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "signature"):
                validate_receipt(receipt_path, paths, public_path)

    def test_build_receipt_rejects_non_boolean_promotion_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._bundle(Path(directory))
            with self.assertRaisesRegex(ValueError, "attestations must be boolean"):
                build_receipt(
                    paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
                    command=["evaluate"], run_id="run-1",
                    timestamp="2026-09-09T00:00:00Z",
                    attestations={"validation_passed": "true"},
                )

    def test_repository_signer_registry_is_fail_closed_by_default(self):
        self.assertEqual(trusted_receipt_signers(), frozenset())
        with tempfile.TemporaryDirectory() as directory:
            private = Ed25519PrivateKey.generate()
            public_path = Path(directory) / "public.key"
            public_path.write_text(base64.b64encode(
                private.public_key().public_bytes_raw()).decode("ascii"), encoding="ascii")
            self.assertFalse(receipt_signer_is_trusted(public_path, "b" * 64))

    def test_eager_report_requires_repository_trust_and_bound_attestations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            manifest = []
            metrics = []
            for index in range(12):
                scene = f"s{index}"
                manifest.append({
                    "scene_id": scene, "source_body": "source", "target_body": "target",
                    "illumination_id": "daylight", "source_path": f"{scene}.raw",
                    "target_path": f"{scene}.jpg", "source_sha256": f"{index:064x}",
                    "target_sha256": f"{index + 100:064x}", "split": "lockbox",
                    "evidence_tier": "C",
                })
                metrics.append({"scene_id": scene, "baseline_delta_e00": 10.,
                                "candidate_delta_e00": 8.})
            values = {
                "manifest": manifest, "metrics": metrics,
                "controls": {name: True for name in (
                    "identity_baseline", "target_reference_shuffle", "source_label_shuffle",
                    "holdout_rerun", "chart_positive_control")},
                "robustness": {"daylight": True},
            }
            for name, value in values.items():
                path = root / f"{name}.json"
                path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
                paths[name] = path
            private = Ed25519PrivateKey.generate()
            public_path = root / "public.key"
            public_path.write_text(base64.b64encode(
                private.public_key().public_bytes_raw()).decode("ascii"), encoding="ascii")

            legacy_receipt = sign_receipt(build_receipt(
                paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
                command=["trusted-evaluator"], run_id="legacy-run",
                timestamp="2026-09-09T00:00:00Z"), private, key_id="ci")
            legacy_path = root / "legacy-receipt.json"
            legacy_path.write_text(json.dumps(legacy_receipt), encoding="utf-8")
            with patch("hybrid_engine.evaluation.eager_cli.receipt_signer_is_trusted",
                       return_value=True):
                with self.assertRaisesRegex(ValueError, "missing promotion attestations"):
                    eager_report(
                        *(str(paths[name]) for name in ("manifest", "metrics", "controls", "robustness")),
                        "C", True, True, True, n_bootstrap=50,
                        receipt_path=str(legacy_path), receipt_public_key_path=str(public_path),
                        expected_git_sha="a" * 40,
                    )

            receipt = sign_receipt(build_receipt(
                paths, git_sha="a" * 40, evaluator_sha256="b" * 64,
                command=["trusted-evaluator"], run_id="run-1",
                timestamp="2026-09-09T00:00:00Z",
                attestations={
                    "validation_passed": True,
                    "lockbox_passed": True,
                    "external_replication": True,
                }), private, key_id="ci")
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            # Replaying the old attack is inert: runtime environment variables
            # can no longer choose the trust root for the official classifier.
            with patch.dict(os.environ, {
                "HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256": public_key_sha256(public_path),
                "HNCS_TRUSTED_EVALUATOR_SHA256": "b" * 64,
            }, clear=True):
                untrusted = eager_report(
                    *(str(paths[name]) for name in ("manifest", "metrics", "controls", "robustness")),
                    "C", True, True, True, n_bootstrap=50,
                    receipt_path=str(receipt_path), receipt_public_key_path=str(public_path),
                    expected_git_sha="a" * 40,
                )
            self.assertEqual(untrusted["classification"]["classification"], "Supported")
            self.assertFalse(untrusted["classification"]["checks"]["trusted_provenance"])

            with patch("hybrid_engine.evaluation.eager_cli.receipt_signer_is_trusted",
                       return_value=True):
                trusted = eager_report(
                    *(str(paths[name]) for name in ("manifest", "metrics", "controls", "robustness")),
                    "C", True, True, True, n_bootstrap=50,
                    receipt_path=str(receipt_path), receipt_public_key_path=str(public_path),
                    expected_git_sha="a" * 40,
                )
            self.assertEqual(trusted["classification"]["classification"], "Verified")

            for index, field in enumerate((
                    "validation_passed", "lockbox_passed", "external_replication")):
                flags = [True, True, True]
                flags[index] = False
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError, f"attestation {field}"):
                        eager_report(
                            *(str(paths[name]) for name in ("manifest", "metrics", "controls", "robustness")),
                            "C", *flags, n_bootstrap=50,
                            receipt_path=str(receipt_path), receipt_public_key_path=str(public_path),
                            expected_git_sha="a" * 40,
                        )

            changed_metrics = [dict(row) for row in metrics]
            changed_metrics[0]["candidate_delta_e00"] = 7.9
            paths["metrics"].write_text(json.dumps(changed_metrics, sort_keys=True), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metrics"):
                eager_report(
                    *(str(paths[name]) for name in ("manifest", "metrics", "controls", "robustness")),
                    "C", True, True, True, n_bootstrap=50,
                    receipt_path=str(receipt_path), receipt_public_key_path=str(public_path),
                    expected_git_sha="a" * 40,
                )


if __name__ == "__main__":
    unittest.main()
