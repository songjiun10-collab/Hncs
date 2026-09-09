import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.fuji.fit_nare_provia_session_holdout import _load_frame, fit, main


def _row(tmp, scene, session, split="evaluation"):
    raw = Path(tmp) / f"{scene}.RAF"
    jpeg = Path(tmp) / f"{scene}.JPG"
    raw.write_bytes(f"raw-{scene}".encode())
    jpeg.write_bytes(f"jpeg-{scene}".encode())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {"scene_id": scene, "session_id": session, "contributor": "test",
            "source_path": str(raw), "target_path": str(jpeg),
            "source_sha256": digest(raw), "target_sha256": digest(jpeg),
            "picture_style": "F0/Standard (Provia)", "lighting": "daylight",
            "scene_type": "natural_scene", "split": split}


class TestNARESessionHoldout(unittest.TestCase):
    def test_invalid_later_input_never_reaches_frame_loader(self):
        for defect in ('source_path', 'target_path', 'picture_style', 'split'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                rows = [_row(tmp, f's{i}', f'session-{i}') for i in range(3)]
                if defect.endswith('_path'):
                    Path(rows[-1][defect]).write_bytes(b'changed')
                else:
                    rows[-1][defect] = 'Classic Chrome' if defect == 'picture_style' else 'lockbox'
                with patch('tools.fuji.fit_nare_provia_session_holdout._load_frame') as load:
                    with self.assertRaises(ValueError):
                        fit(rows)
                    load.assert_not_called()

    def test_relabelled_content_cannot_cross_holdout_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [_row(tmp, f's{i}', f'session-{i}') for i in range(3)]
            for row in rows[1:]:
                row.update(source_path=rows[0]['source_path'], source_sha256=rows[0]['source_sha256'])
            with patch('tools.fuji.fit_nare_provia_session_holdout._load_frame') as load:
                with self.assertRaisesRegex(ValueError, 'duplicate'):
                    fit(rows)
                load.assert_not_called()

    def test_frame_loader_rejects_aspect_ratio_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = _row(tmp, "scene-1", "session-1")
            source = np.zeros((100, 100, 3), dtype=np.uint8)
            target = np.zeros((100, 200, 3), dtype=np.uint8)
            with patch("tools.fuji.fit_nare_provia_session_holdout.load_neutral_render",
                       return_value=source), \
                 patch("tools.fuji.fit_nare_provia_session_holdout.cv2.imread",
                       return_value=target), \
                 patch("tools.fuji.fit_nare_provia_session_holdout.register_to_target") as register:
                with self.assertRaisesRegex(ValueError, "aspect ratios differ"):
                    _load_frame(row, max_dim=512)
                register.assert_not_called()

    def test_selection_uses_training_sessions_only_after_real_hash_validation(self):
        # The held-out scene strongly prefers the other parameter: including it
        # in training changes the selected parameter and fails this assertion.
        with tempfile.TemporaryDirectory() as tmp:
            rows = [_row(tmp, f's{i}', f'session-{i}') for i in range(3)]
            def score(frame, shoulder, clip):
                if (shoulder, clip) == (0.82, 3.0):
                    return 20.0
                return ([0., 10.] if frame['scene_id'] == 's0' else [4., 0.])[int(shoulder)]
            with patch('tools.fuji.fit_nare_provia_session_holdout._load_frame',
                       side_effect=lambda row, max_dim: row), \
                 patch('tools.fuji.fit_nare_provia_session_holdout.GRID', [(0., 1.), (1., 1.)]), \
                 patch('tools.fuji.fit_nare_provia_session_holdout._score', side_effect=score):
                result = fit(rows)
            self.assertEqual([fold['shoulder_start'] for fold in result['folds']], [1., 0., 0.])
            self.assertTrue(all(fold['n_train'] == 2 and fold['n_test'] == 1 for fold in result['folds']))

    def test_fit_rejects_lockbox_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [_row(tmp, f"s{i}", f"session-{i}", "lockbox") for i in range(3)]
            with self.assertRaisesRegex(ValueError, "evaluation"):
                fit(rows)

    def test_fit_rejects_duplicate_scene_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [_row(tmp, "same", f"session-{i}") for i in range(3)]
            with self.assertRaisesRegex(ValueError, "duplicate|conflicting"):
                fit(rows)

    def test_cli_accepts_documented_candidate_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            output = Path(tmp) / "fit.json"
            manifest.write_text("[]", encoding="utf-8")
            with patch("tools.fuji.fit_nare_provia_session_holdout.fit",
                       return_value={"n_sessions": 3, "n_scenes": 3}):
                main(["--manifest", str(manifest), "--candidate", "provia",
                      "--out", str(output)])
            self.assertEqual(json.loads(output.read_text())["n_scenes"], 3)


if __name__ == "__main__":
    unittest.main()
