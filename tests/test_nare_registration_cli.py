import unittest
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from hybrid_engine.evaluation.nare_registration_cli import build_report, main


def row(scene_id):
    return {"scene_id": scene_id, "session_id": "s", "contributor": "c",
            "source_path": f"{scene_id}.RAF", "target_path": f"{scene_id}.JPG",
            "source_sha256": hashlib.sha256(f"raw-{scene_id}".encode()).hexdigest(),
            "target_sha256": hashlib.sha256(f"jpeg-{scene_id}".encode()).hexdigest(),
            "picture_style": "F0/Standard (Provia)", "lighting": "daylight",
            "scene_type": "natural_scene", "split": "evaluation"}


class TestNARERegistrationCLI(unittest.TestCase):
    def test_accounts_for_passes_and_failures(self):
        image = np.zeros((4, 4, 3), dtype=np.uint8)
        with patch("hybrid_engine.evaluation.nare_registration_cli.load_neutral_render", return_value=image), \
             patch("hybrid_engine.evaluation.nare_registration_cli.cv2.imread", return_value=image), \
             patch("hybrid_engine.evaluation.nare_registration_cli.inspect_registration",
                   side_effect=[{"passed": True, "failure_reason": None},
                                {"passed": False, "failure_reason": "correlation"}]):
            report = build_report([row("a"), row("b")], max_dim=512)
        self.assertEqual(report["n_input"], 2)
        self.assertEqual(report["n_passed"], 1)
        self.assertEqual(report["failure_counts"], {"correlation": 1})

    def test_cli_writes_only_registration_passed_manifest_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            report = Path(directory) / "report.json"
            passed = Path(directory) / "passed.json"
            manifest.write_text(json.dumps([row("a"), row("b")]), encoding="utf-8")
            with patch("hybrid_engine.evaluation.nare_registration_cli.build_report",
                       return_value={"n_input": 2, "n_passed": 1, "failure_counts": {},
                                     "records": [{"scene_id": "a", "passed": True},
                                                 {"scene_id": "b", "passed": False}]}):
                main(["--manifest", str(manifest), "--out", str(report),
                      "--passed-manifest-out", str(passed)])
            self.assertEqual([item["scene_id"] for item in json.loads(passed.read_text())], ["a"])


if __name__ == "__main__":
    unittest.main()
