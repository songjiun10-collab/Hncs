import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.fuji.fit_nare_provia_session_holdout import fit, main


def _row(tmp, scene, session, split="evaluation"):
    raw = Path(tmp) / f"{scene}.RAF"
    jpeg = Path(tmp) / f"{scene}.JPG"
    raw.write_bytes(b"raw")
    jpeg.write_bytes(b"jpeg")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {"scene_id": scene, "session_id": session, "contributor": "test",
            "source_path": str(raw), "target_path": str(jpeg),
            "source_sha256": digest(raw), "target_sha256": digest(jpeg),
            "picture_style": "F0/Standard (Provia)", "lighting": "daylight",
            "scene_type": "natural_scene", "split": split}


class TestNARESessionHoldout(unittest.TestCase):
    def test_fit_rejects_lockbox_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [_row(tmp, f"s{i}", f"session-{i}", "lockbox") for i in range(3)]
            with self.assertRaisesRegex(ValueError, "evaluation"):
                fit(rows)

    def test_fit_rejects_duplicate_scene_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [_row(tmp, "same", f"session-{i}") for i in range(3)]
            with self.assertRaisesRegex(ValueError, "duplicate"):
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
