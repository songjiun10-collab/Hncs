"""TestSummarizeRecordedRun for the GFX100RF Provia NARE 512px run.

Per-scene ΔE00 pairs hardcoded from the frozen, committed report
``datasets/fuji/contributed/dpreview-gfx100rf-preprod-2026-08/
nare_provia_registered_report_512px_2026-09.json`` (37 scenes, sorted by
scene_id, matching ``aggregate_scene_metrics``'s own sort order). Feeding
them back through ``evaluate_paired`` must reproduce the statistics
published in ``hybrid_engine/EVALUATION.md``'s corrected 37-frame
exploratory replay, without re-running the RAW decode/registration
pipeline (hours).
"""

import unittest

from hybrid_engine.evaluation.eager import SceneMetric, evaluate_paired

# (scene_id, baseline_delta_e00, candidate_delta_e00)
_ROWS = [
    ("gfx100rf-000", 19.77187768621074, 13.33607141738031),
    ("gfx100rf-001", 13.418790401597953, 11.540335424712387),
    ("gfx100rf-004", 20.52718664488509, 16.9558046972647),
    ("gfx100rf-005", 19.833110497583696, 12.073575357927705),
    ("gfx100rf-006", 20.432267715650717, 13.698572778552721),
    ("gfx100rf-007", 24.03010832591789, 16.793388508294967),
    ("gfx100rf-009", 20.846678819950952, 15.228457300990467),
    ("gfx100rf-010", 20.817338955010612, 20.131162257130754),
    ("gfx100rf-013", 7.41506180109306, 5.88183487782764),
    ("gfx100rf-015", 20.10777320031094, 12.105688225312786),
    ("gfx100rf-016", 16.99140559105267, 13.741492238328055),
    ("gfx100rf-017", 16.21671224062985, 10.14416126020018),
    ("gfx100rf-018", 19.411853644335167, 13.912297363010639),
    ("gfx100rf-020", 17.751526537578712, 12.262651369943798),
    ("gfx100rf-022", 4.396772232847536, 4.544815339930816),
    ("gfx100rf-026", 16.03679390852091, 9.65039667395424),
    ("gfx100rf-027", 11.755377391914738, 8.389338958291843),
    ("gfx100rf-028", 15.188458596841471, 11.97791997615344),
    ("gfx100rf-029", 13.474758152619488, 7.247808214746592),
    ("gfx100rf-030", 6.853202315734399, 5.925307885696843),
    ("gfx100rf-031", 20.715833858885343, 11.454190054829386),
    ("gfx100rf-032", 21.41392850023431, 13.074550215179576),
    ("gfx100rf-033", 20.754351662317845, 14.74240531903522),
    ("gfx100rf-034", 19.497253218748085, 12.12977776212567),
    ("gfx100rf-035", 16.928947493805797, 10.088531081930347),
    ("gfx100rf-040", 17.18510601013344, 12.079043884305124),
    ("gfx100rf-041", 23.78663582465107, 16.2624121231471),
    ("gfx100rf-042", 19.470684345563264, 13.8376403671603),
    ("gfx100rf-043", 25.059936414015116, 16.775685596021756),
    ("gfx100rf-044", 10.283864490155816, 7.843608753654587),
    ("gfx100rf-045", 10.517726633242209, 8.37640069883164),
    ("gfx100rf-046", 7.488665996353775, 7.0912147104306404),
    ("gfx100rf-047", 10.151568137711003, 7.420693136525423),
    ("gfx100rf-048", 6.13329145238757, 3.84415732689898),
    ("gfx100rf-050", 18.805929122425027, 19.318431921748445),
    ("gfx100rf-051", 19.536922628813628, 16.895244030571405),
    ("gfx100rf-052", 18.27663832332503, 16.844055221737225),
]


class TestSummarizeRecordedRun(unittest.TestCase):
    """Reproduce the published GFX100RF Provia 512px NARE statistics."""

    def test_reproduces_published_statistics(self):
        metrics = [SceneMetric(scene_id=scene_id, baseline_delta_e00=baseline,
                                candidate_delta_e00=candidate)
                   for scene_id, baseline, candidate in _ROWS]
        result = evaluate_paired(metrics)

        self.assertEqual(result["n_scenes"], 37)
        self.assertAlmostEqual(result["mean_baseline"], 16.5211983452177, places=6)
        self.assertAlmostEqual(result["mean_candidate"], 11.989706008913075, places=6)
        self.assertAlmostEqual(result["mean_improvement_pct"], 27.42835139205464, places=6)
        self.assertAlmostEqual(result["ci95"][0], 3.6717888562545196, places=6)
        self.assertAlmostEqual(result["ci95"][1], 5.400666505888509, places=6)
        self.assertAlmostEqual(result["sign_test_p"], 1.0244548320770264e-08, places=14)


if __name__ == "__main__":
    unittest.main()
