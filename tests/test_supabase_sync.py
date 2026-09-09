import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hybrid_engine.evaluation.supabase_sync import (
    SupabaseRestClient,
    sha256_file,
    sync_evaluation_report,
)


class _FakeClient:
    def __init__(self):
        self.calls = []

    def upsert(self, table, rows, on_conflict):
        copied = [dict(row) for row in rows]
        self.calls.append((table, copied, on_conflict))
        if table == "hncs_datasets":
            return [{"id": "dataset-1", **copied[0]}]
        if table == "hncs_runs":
            return [{"id": "run-1", **copied[0]}]
        return copied


class TestSupabaseSync(unittest.TestCase):
    def test_forged_trust_cannot_authorize_registry_promotion(self):
        for label, ship in (("Verified", True), ("Verified", False),
                            ("Supported", True), ("Supported", False),
                            ("Inconclusive", True)):
            with self.subTest(label=label, ship=ship), tempfile.TemporaryDirectory() as tmp:
                manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s"}])
                metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
                report = {
                    "paired": {"trusted_provenance": True, "per_scene": [
                        {"scene_id": "s", "baseline_delta_e00": 2.,
                         "candidate_delta_e00": 1.}]},
                    "classification": {"classification": label, "ship_gate_passed": ship},
                    "receipt": {"trusted": True, "replay_passed": True},
                }
                client = _FakeClient()
                with self.assertRaisesRegex(ValueError, "independent verification"):
                    sync_evaluation_report(
                        report, protocol="NARE", dataset_slug="d", candidate_name="c",
                        manifest_path=manifest, metrics_path=metrics, client=client)
                self.assertEqual(client.calls, [])

    def test_registry_requires_literal_boolean_gate_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s", "split": "evaluation"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {
                    "provenance_passed": "false",
                    "per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.0,
                                   "candidate_delta_e00": 1.0}],
                },
                "classification": {
                    "classification": "Inconclusive",
                    "ship_gate_passed": "false",
                },
            }
            client = _FakeClient()
            result = sync_evaluation_report(
                report, protocol="NARE", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics,
                external_replication="false", client=client)
            self.assertFalse(result["ship_gate"])
            by_table = {table: rows for table, rows, _ in client.calls}
            self.assertEqual(by_table["hncs_datasets"][0]["provenance_status"], "incomplete")
            self.assertFalse(by_table["hncs_runs"][0]["provenance_complete"])
            self.assertFalse(by_table["hncs_runs"][0]["external_replication"])

    def _write_json(self, root, name, value):
        path = Path(root) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_credentials_are_required_and_https_only(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HNCS_SUPABASE_URL"):
                SupabaseRestClient()
        with self.assertRaisesRegex(ValueError, "https"):
            SupabaseRestClient("http://example.invalid", "service-role-key")

    def test_sync_preserves_classification_and_scene_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [
                {
                    "scene_id": "scene-1",
                    "source_body": "GFX100RF",
                    "target_body": "GFX100RF",
                    "illumination_id": "daylight",
                    "lighting": "daylight",
                    "scene_type": "natural_scene",
                    "session_id": "session-a",
                    "contributor": "dpreview",
                    "picture_style": "unknown",
                    "split": "evaluation",
                },
                {
                    "scene_id": "scene-2",
                    "source_body": "GFX100RF",
                    "target_body": "GFX100RF",
                    "illumination_id": "tungsten",
                    "lighting": "tungsten",
                    "scene_type": "portrait",
                    "session_id": "session-b",
                    "contributor": "tester",
                    "picture_style": "Provia",
                    "split": "evaluation",
                },
            ])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "scene-1"}, {"scene_id": "scene-2"}])
            controls = self._write_json(tmp, "controls.json", {"controls_passed": True})
            report_path = self._write_json(tmp, "report.json", {"placeholder": True})
            report = {
                "paired": {
                    "n_scenes": 2,
                    "mean_baseline": 10.0,
                    "mean_candidate": 8.5,
                    "mean_improvement": 1.5,
                    "mean_improvement_pct": 15.0,
                    "ci95": [0.5, 2.5],
                    "sign_test_p": 0.5,
                    "provenance_passed": False,
                    "coverage": {
                        "lighting": ["daylight", "tungsten"],
                        "scene_type": ["natural_scene", "portrait"],
                    },
                    "per_scene": [
                        {
                            "scene_id": "scene-1",
                            "baseline_delta_e00": 11.0,
                            "candidate_delta_e00": 9.0,
                            "improvement": 2.0,
                        },
                        {
                            "scene_id": "scene-2",
                            "baseline_delta_e00": 9.0,
                            "candidate_delta_e00": 8.0,
                            "improvement": 1.0,
                        },
                    ],
                },
                "classification": {
                    "ship_gate_passed": False,
                    "classification": "Inconclusive",
                },
            }
            expected_manifest_sha = sha256_file(manifest)
            client = _FakeClient()
            result = sync_evaluation_report(
                report,
                protocol="NARE",
                dataset_slug="gfx100rf-nare-pilot",
                candidate_name="provia",
                manifest_path=manifest,
                metrics_path=metrics,
                controls_path=controls,
                report_path=report_path,
                evidence_tier="C",
                brand="Fujifilm",
                camera_model="GFX100RF",
                git_sha="7777777777777777777777777777777777777777",
                bootstrap_draws=20_000,
                bootstrap_seed=0,
                client=client,
            )

        self.assertEqual(result["classification"], "Inconclusive")
        self.assertFalse(result["ship_gate"])
        self.assertEqual(result["n_scenes"], 2)

        by_table = {table: (rows, conflict) for table, rows, conflict in client.calls}
        dataset_rows, dataset_conflict = by_table["hncs_datasets"]
        self.assertEqual(dataset_conflict, "slug")
        self.assertEqual(dataset_rows[0]["provenance_status"], "incomplete")
        self.assertEqual(dataset_rows[0]["manifest_sha256"], expected_manifest_sha)

        run_rows, run_conflict = by_table["hncs_runs"]
        self.assertEqual(run_conflict, "run_key")
        self.assertEqual(run_rows[0]["classification"], "Inconclusive")
        self.assertFalse(run_rows[0]["ship_gate"])
        self.assertEqual(run_rows[0]["git_sha"], "7777777777777777777777777777777777777777")

        scene_rows, scene_conflict = by_table["hncs_scene_metrics"]
        self.assertEqual(scene_conflict, "run_id,scene_id")
        self.assertEqual(len(scene_rows), 2)
        self.assertEqual(scene_rows[1]["scene_category"], "portrait")
        self.assertEqual(scene_rows[1]["illumination_id"], "tungsten")
        self.assertEqual(scene_rows[1]["metadata"]["picture_style"], "Provia")

    def test_same_frozen_inputs_produce_same_run_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [
                {"scene_id": "s", "split": "evaluation"},
            ])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {
                    "n_scenes": 1,
                    "mean_baseline": 2.0,
                    "mean_candidate": 1.0,
                    "mean_improvement": 1.0,
                    "mean_improvement_pct": 50.0,
                    "ci95": [1.0, 1.0],
                    "sign_test_p": 1.0,
                    "per_scene": [{
                        "scene_id": "s",
                        "baseline_delta_e00": 2.0,
                        "candidate_delta_e00": 1.0,
                    }],
                },
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            first = sync_evaluation_report(
                report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, git_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                client=_FakeClient(),
            )
            second = sync_evaluation_report(
                report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, git_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                client=_FakeClient(),
            )
        self.assertEqual(first["run_key"], second["run_key"])

    def test_run_key_changes_when_control_artifact_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            controls = self._write_json(tmp, "controls.json", {"controls_passed": False})
            report = {
                "paired": {"per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.,
                                               "candidate_delta_e00": 1.}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            first = sync_evaluation_report(
                report, protocol="NARE", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, controls_path=controls,
                client=_FakeClient())
            controls.write_text(json.dumps({"controls_passed": True}), encoding="utf-8")
            second = sync_evaluation_report(
                report, protocol="NARE", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, controls_path=controls,
                client=_FakeClient())
        self.assertNotEqual(first["run_key"], second["run_key"])

    def test_run_key_changes_when_git_revision_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {"per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.,
                                               "candidate_delta_e00": 1.}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            first = sync_evaluation_report(
                report, protocol="NARE", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, git_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                client=_FakeClient())
            second = sync_evaluation_report(
                report, protocol="NARE", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, git_sha="cccccccccccccccccccccccccccccccccccccccc",
                client=_FakeClient())
        self.assertNotEqual(first["run_key"], second["run_key"])

    def test_registry_rejects_abbreviated_git_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {"per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.0,
                                            "candidate_delta_e00": 1.0}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            with self.assertRaisesRegex(ValueError, "full 40-character"):
                sync_evaluation_report(
                    report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, git_sha="abc1234",
                    client=_FakeClient())

    def test_invalid_scene_metrics_are_rejected_before_any_registry_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {"per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.0,
                                            "candidate_delta_e00": float("nan")}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            client = _FakeClient()
            with self.assertRaisesRegex(ValueError, "ΔE values"):
                sync_evaluation_report(
                    report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, client=client)
            self.assertEqual(client.calls, [])

    def test_inconsistent_aggregate_metrics_are_rejected_before_registry_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {"mean_baseline": 99.0, "mean_candidate": 1.0,
                            "mean_improvement": 98.0, "mean_improvement_pct": 98.99,
                            "per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.0,
                                            "candidate_delta_e00": 1.0}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            client = _FakeClient()
            with self.assertRaisesRegex(ValueError, "aggregate metrics"):
                sync_evaluation_report(
                    report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, client=client)
            self.assertEqual(client.calls, [])

    def test_invalid_statistical_envelope_is_rejected_before_registry_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {"ci95": [2.0, 1.0], "sign_test_p": 2.0,
                            "per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.0,
                                            "candidate_delta_e00": 1.0}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            client = _FakeClient()
            with self.assertRaisesRegex(ValueError, "ci95"):
                sync_evaluation_report(
                    report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, client=client)
            self.assertEqual(client.calls, [])

    def test_ship_gate_cannot_be_synced_without_trusted_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s", "split": "evaluation"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {
                    "n_scenes": 1,
                    "per_scene": [{"scene_id": "s", "baseline_delta_e00": 2.0,
                                   "candidate_delta_e00": 1.0}],
                },
                "classification": {"ship_gate_passed": True, "classification": "Supported"},
            }
            with self.assertRaisesRegex(ValueError, "trusted provenance"):
                sync_evaluation_report(
                    report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, git_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    client=_FakeClient(),
                )

    def test_verified_label_cannot_be_synced_without_trusted_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s", "split": "evaluation"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s"}])
            report = {
                "paired": {"n_scenes": 1, "per_scene": [
                    {"scene_id": "s", "baseline_delta_e00": 2.0, "candidate_delta_e00": 1.0}
                ]},
                "classification": {"ship_gate_passed": False, "classification": "Verified"},
            }
            with self.assertRaisesRegex(ValueError, "trusted provenance"):
                sync_evaluation_report(
                    report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, git_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    client=_FakeClient(),
                )

    def test_scene_lineage_rejects_unknown_or_duplicate_report_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s1"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s1"}])
            base = {"classification": {"ship_gate_passed": False, "classification": "Exploratory"}}
            for rows in (
                [{"scene_id": "unknown", "baseline_delta_e00": 2.0, "candidate_delta_e00": 1.0}],
                [{"scene_id": "s1", "baseline_delta_e00": 2.0, "candidate_delta_e00": 1.0},
                 {"scene_id": "s1", "baseline_delta_e00": 2.0, "candidate_delta_e00": 1.0}],
            ):
                with self.subTest(rows=rows):
                    report = {"paired": {"per_scene": rows}, **base}
                    with self.assertRaisesRegex(ValueError, "scene_id"):
                        sync_evaluation_report(
                            report, protocol="NARE", dataset_slug="d", candidate_name="c",
                            manifest_path=manifest, metrics_path=metrics, client=_FakeClient())

    def test_scene_lineage_rejects_metrics_artifact_from_another_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s1"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "different"}])
            report = {
                "paired": {"per_scene": [{"scene_id": "s1", "baseline_delta_e00": 2.0,
                                            "candidate_delta_e00": 1.0}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            with self.assertRaisesRegex(ValueError, "metrics, manifest"):
                sync_evaluation_report(
                    report, protocol="NARE", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, client=_FakeClient())

    def test_nare_scene_lineage_rejects_metrics_value_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s1"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s1",
                                                               "raw_delta_e00": 99.0,
                                                               "candidate_delta_e00": 1.0}])
            report = {
                "paired": {"per_scene": [{"scene_id": "s1", "baseline_delta_e00": 2.0,
                                            "candidate_delta_e00": 1.0}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            with self.assertRaisesRegex(ValueError, "values do not match"):
                sync_evaluation_report(
                    report, protocol="NARE", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, client=_FakeClient())

    def test_eager_scene_lineage_rejects_metrics_value_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._write_json(tmp, "manifest.json", [{"scene_id": "s1"}])
            metrics = self._write_json(tmp, "metrics.json", [{"scene_id": "s1",
                                                               "baseline_delta_e00": 99.0,
                                                               "candidate_delta_e00": 1.0}])
            report = {
                "paired": {"per_scene": [{"scene_id": "s1", "baseline_delta_e00": 2.0,
                                            "candidate_delta_e00": 1.0}]},
                "classification": {"ship_gate_passed": False, "classification": "Exploratory"},
            }
            with self.assertRaisesRegex(ValueError, "values do not match"):
                sync_evaluation_report(
                    report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                    manifest_path=manifest, metrics_path=metrics, client=_FakeClient())


if __name__ == "__main__":
    unittest.main()
