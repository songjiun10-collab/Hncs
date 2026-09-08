import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from hybrid_engine.evaluation.nare_runner import run_nare_metrics
from hybrid_engine.evaluation.nare_runner_cli import main


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _row(tmp, scene_id="scene-1", picture_style="F0/Standard (Provia)"):
    raw = Path(tmp) / f"{scene_id}.RAF"
    jpeg = Path(tmp) / f"{scene_id}.JPG"
    raw.write_bytes(b"raw")
    jpeg.write_bytes(b"jpeg")
    return {
        "scene_id": scene_id, "session_id": "capture-2026-09-08",
        "contributor": "test", "source_path": str(raw), "target_path": str(jpeg),
        "source_sha256": _hash(raw), "target_sha256": _hash(jpeg),
        "picture_style": picture_style, "lighting": "daylight",
        "scene_type": "unknown", "split": "evaluation",
    }


class TestNareRunner(unittest.TestCase):
    def test_measures_three_layers_after_hash_and_style_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = [_row(tmp)]
            neutral = np.zeros((2, 2, 3), dtype=np.uint8)
            target = np.zeros((2, 2, 3), dtype=np.float64)
            with patch("hybrid_engine.evaluation.nare_runner.load_neutral_render", return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.cv2.imread", return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.register_to_target",
                       return_value=(neutral, np.ones((2, 2), dtype=bool), {})), \
                 patch("hybrid_engine.evaluation.nare_runner.mean_delta_e", side_effect=[9.0, 8.0, 7.0]):
                metrics = run_nare_metrics(manifest, "F0/Standard (Provia)",
                                           candidate=lambda image: image,
                                           foundation=lambda image: image, max_dim=512)
        self.assertEqual(metrics, [{"scene_id": "scene-1", "raw_delta_e00": 9.0,
                                    "foundation_delta_e00": 8.0, "candidate_delta_e00": 7.0,
                                    "registration": {}}])

    def test_rejects_mixed_style_and_changed_input_before_decoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            matching = _row(tmp, "scene-1")
            mixed = _row(tmp, "scene-2", picture_style="Classic Chrome")
            with self.assertRaisesRegex(ValueError, "picture_style"):
                run_nare_metrics([matching, mixed], "F0/Standard (Provia)",
                                 candidate=lambda image: image)

            Path(matching["source_path"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source hash"):
                run_nare_metrics([matching], "F0/Standard (Provia)",
                                 candidate=lambda image: image)

    def test_cli_writes_metrics_for_fixed_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, output = Path(tmp) / "manifest.json", Path(tmp) / "metrics.json"
            manifest.write_text("[]", encoding="utf-8")
            with patch("hybrid_engine.evaluation.nare_runner_cli.run_nare_metrics",
                       return_value=[{"scene_id": "scene-1", "raw_delta_e00": 9.0,
                                     "foundation_delta_e00": 9.0,
                                     "candidate_delta_e00": 7.0}]) as run:
                main(["--manifest", str(manifest), "--candidate", "provia", "--out", str(output)])
            self.assertEqual(run.call_args.args[1], "F0/Standard (Provia)")
            self.assertEqual(output.read_text(encoding="utf-8").strip()[0], "[")


if __name__ == "__main__":
    unittest.main()
