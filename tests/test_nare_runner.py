import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import cv2

from hybrid_engine.evaluation.nare_runner import run_nare_metrics
from hybrid_engine.evaluation.nare_runner_cli import main


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _row(tmp, scene_id="scene-1", picture_style="F0/Standard (Provia)"):
    raw = Path(tmp) / f"{scene_id}.RAF"
    jpeg = Path(tmp) / f"{scene_id}.JPG"
    raw.write_bytes(f"raw-{scene_id}".encode())
    jpeg.write_bytes(f"jpeg-{scene_id}".encode())
    return {
        "scene_id": scene_id, "session_id": "capture-2026-09-08",
        "contributor": "test", "source_path": str(raw), "target_path": str(jpeg),
        "source_sha256": _hash(raw), "target_sha256": _hash(jpeg),
        "picture_style": picture_style, "lighting": "daylight",
        "scene_type": "unknown", "split": "evaluation",
    }


class TestNareRunner(unittest.TestCase):
    def test_inplace_transforms_preserve_baselines_and_compose_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = [_row(tmp)]
            target = np.full((8, 8, 3), 120, dtype=np.uint8)
            cv2.imwrite(manifest[0]['target_path'], target)
            manifest[0]['target_sha256'] = _hash(manifest[0]['target_path'])
            neutral = np.full_like(target, 40)
            def foundation(image):
                image += 40
                return image
            def candidate(image):
                image += 40
                return image
            with patch('hybrid_engine.evaluation.nare_runner.load_neutral_render', return_value=neutral), \
                 patch('hybrid_engine.evaluation.nare_runner.register_to_target',
                       side_effect=lambda source, target: (
                           source, np.ones((8, 8), dtype=bool), {"long_edge_px": 512})):
                result = run_nare_metrics(manifest, 'F0/Standard (Provia)',
                                          foundation=foundation, candidate=candidate)[0]
            self.assertGreater(result['raw_delta_e00'], result['foundation_delta_e00'])
            self.assertGreater(result['foundation_delta_e00'], 0)
            self.assertAlmostEqual(result['candidate_delta_e00'], 0)
            np.testing.assert_array_equal(neutral, np.full_like(target, 40))

    def test_measures_three_layers_after_hash_and_style_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = [_row(tmp)]
            neutral = np.zeros((2, 2, 3), dtype=np.uint8)
            target = np.zeros((2, 2, 3), dtype=np.float64)
            with patch("hybrid_engine.evaluation.nare_runner.load_neutral_render", return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.cv2.imread", return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.register_to_target",
                       return_value=(neutral, np.ones((2, 2), dtype=bool),
                                     {"long_edge_px": 512})), \
                 patch("hybrid_engine.evaluation.nare_runner.mean_delta_e", side_effect=[9.0, 8.0, 7.0]):
                metrics = run_nare_metrics(manifest, "F0/Standard (Provia)",
                                           candidate=lambda image: image,
                                           foundation=lambda image: image, max_dim=512)
        self.assertEqual(metrics, [{"scene_id": "scene-1", "raw_delta_e00": 9.0,
                                    "foundation_delta_e00": 8.0, "candidate_delta_e00": 7.0,
                                    "registration": {"long_edge_px": 512}}])

    def test_candidate_receives_foundation_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = [_row(tmp)]
            neutral = np.zeros((2, 2, 3), dtype=np.uint8)
            foundation_input = []
            candidate_input = []
            def foundation(image):
                foundation_input.append(image.copy())
                return image + 1
            def candidate(image):
                candidate_input.append(image.copy())
                return image
            with patch("hybrid_engine.evaluation.nare_runner.load_neutral_render", return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.cv2.imread", return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.register_to_target",
                       return_value=(neutral, np.ones((2, 2), dtype=bool),
                                     {"ecc_correlation": .9, "overlap_fraction": .99,
                                      "long_edge_px": 512})), \
                 patch("hybrid_engine.evaluation.nare_runner.mean_delta_e", return_value=1.0):
                run_nare_metrics(manifest, "F0/Standard (Provia)",
                                 candidate=candidate, foundation=foundation, max_dim=512)
            self.assertEqual(len(foundation_input), 1)
            self.assertEqual(len(candidate_input), 1)
            np.testing.assert_array_equal(candidate_input[0], foundation_input[0] + 1)

    def test_rejects_aspect_ratio_mismatch_before_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = [_row(tmp)]
            neutral = np.zeros((2, 2, 3), dtype=np.uint8)
            target = np.zeros((2, 3, 3), dtype=np.uint8)
            with patch("hybrid_engine.evaluation.nare_runner.load_neutral_render",
                       return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.cv2.imread",
                       return_value=target), \
                 patch("hybrid_engine.evaluation.nare_runner.register_to_target") as register:
                with self.assertRaisesRegex(ValueError, "aspect ratios differ"):
                    run_nare_metrics(manifest, "F0/Standard (Provia)",
                                     candidate=lambda image: image)
                register.assert_not_called()

    def test_allows_small_decoder_aspect_ratio_rounding(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = [_row(tmp)]
            neutral = np.zeros((100, 133, 3), dtype=np.uint8)
            target = np.zeros((100, 132, 3), dtype=np.uint8)
            with patch("hybrid_engine.evaluation.nare_runner.load_neutral_render",
                       return_value=neutral), \
                 patch("hybrid_engine.evaluation.nare_runner.cv2.imread",
                       return_value=target), \
                 patch("hybrid_engine.evaluation.nare_runner.register_to_target",
                       return_value=(neutral, np.ones((100, 133), dtype=bool),
                                     {"long_edge_px": 133})), \
                 patch("hybrid_engine.evaluation.nare_runner.mean_delta_e",
                       return_value=1.0):
                result = run_nare_metrics(manifest, "F0/Standard (Provia)",
                                          candidate=lambda image: image)
            self.assertEqual(result[0]["registration"]["long_edge_px"], 133)

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

    def test_later_row_hash_mismatch_is_caught_before_any_row_is_decoded(self):
        """모듈 docstring의 계약("verifies the frozen source hashes ...
        before decoding any RAW file")이 다중 row에서도 실제로 지켜지는지 -
        고치기 전엔 3번째 row 해시가 깨져도 1·2번 row는 이미 디코드된 뒤에
        실패했다."""
        with tempfile.TemporaryDirectory() as tmp:
            rows = [_row(tmp, f"scene-{i}") for i in range(1, 4)]
            Path(rows[2]["source_path"]).write_bytes(b"corrupted")
            with patch("hybrid_engine.evaluation.nare_runner.load_neutral_render") as decode:
                with self.assertRaisesRegex(ValueError, "source hash"):
                    run_nare_metrics(rows, "F0/Standard (Provia)",
                                     candidate=lambda image: image)
                self.assertEqual(decode.call_count, 0,
                                 "앞선 row가 손상된 뒤쪽 row보다 먼저 디코드됨 - "
                                 "hash 검증이 배치 전체보다 먼저 끝나지 않음")

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
