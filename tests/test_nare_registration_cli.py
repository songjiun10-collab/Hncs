import unittest
from unittest.mock import patch

import numpy as np

from hybrid_engine.evaluation.nare_registration_cli import build_report


def row(scene_id):
    return {"scene_id": scene_id, "session_id": "s", "contributor": "c",
            "source_path": f"{scene_id}.RAF", "target_path": f"{scene_id}.JPG",
            "source_sha256": "a" * 64, "target_sha256": "b" * 64,
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


if __name__ == "__main__":
    unittest.main()
