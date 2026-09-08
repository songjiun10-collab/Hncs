import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestNARECLI(unittest.TestCase):
    def test_cli_emits_three_layer_report(self):
        manifest = []
        metrics = []
        for i in range(12):
            scene = f"s{i:02d}"
            manifest.append({
                "scene_id": scene, "session_id": f"session-{i}", "contributor": f"p{i%2}",
                "source_path": f"{scene}.raw", "target_path": f"{scene}.jpg",
                "source_sha256": "a" * 64, "target_sha256": "b" * 64,
                "picture_style": "standard", "lighting": ["daylight", "tungsten", "mixed"][i % 3],
                "scene_type": ["portrait", "landscape", "indoor"][i % 3],
                "split": "evaluation",
            })
            metrics.append({"scene_id": scene, "raw_delta_e00": 10,
                            "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                            "registration": {"ecc_correlation": 0.9,
                                             "overlap_fraction": 0.99}})
        controls = {"subgroups_passed": True, "controls_passed": True,
                    "provenance_passed": True}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (("manifest", manifest), ("metrics", metrics), ("controls", controls)):
                (root / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
            proc = subprocess.run([
                sys.executable, "-m", "hybrid_engine.evaluation.nare_cli",
                "--manifest", str(root / "manifest.json"), "--metrics", str(root / "metrics.json"),
                "--controls", str(root / "controls.json"), "--bootstrap", "200", "--seed", "0",
            ], capture_output=True, text=True, check=True)
        report = json.loads(proc.stdout)
        self.assertTrue(report["classification"]["ship_gate_passed"])
        self.assertEqual(report["classification"]["classification"], "Supported")
        self.assertEqual(report["paired"]["n_scenes"], 12)


if __name__ == "__main__":
    unittest.main()
