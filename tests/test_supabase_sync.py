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
                git_sha="79bf33e",
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
        self.assertEqual(run_rows[0]["git_sha"], "79bf33e")

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
                "classification": {"ship_gate_passed": False, "classification": "Supported"},
            }
            first = sync_evaluation_report(
                report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, git_sha="abcdef1",
                client=_FakeClient(),
            )
            second = sync_evaluation_report(
                report, protocol="EAGER", dataset_slug="d", candidate_name="c",
                manifest_path=manifest, metrics_path=metrics, git_sha="abcdef1",
                client=_FakeClient(),
            )
        self.assertEqual(first["run_key"], second["run_key"])


if __name__ == "__main__":
    unittest.main()
