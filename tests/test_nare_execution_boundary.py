import unittest
import tempfile
import json
import base64
from pathlib import Path
from unittest.mock import patch
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hybrid_engine.evaluation.nare import _registration_is_valid
from hybrid_engine.evaluation.nare_runner import _aggregate_scene_metrics


class TestSceneRegistration(unittest.TestCase):
    def diagnostic(self, **changes):
        return dict(dict(ecc_correlation=.99, overlap_fraction=.99,
                         shift_x_px=0., shift_y_px=0., long_edge_px=512), **changes)

    def aggregate(self, *diagnostics):
        return _aggregate_scene_metrics([
            dict(scene_id='s', raw_delta_e00=10., foundation_delta_e00=8.,
                 candidate_delta_e00=5., registration=d) for d in diagnostics
        ])[0]['registration']

    def test_orthogonal_shifts_do_not_create_a_fictitious_vector(self):
        self.assertTrue(_registration_is_valid(self.aggregate(
            self.diagnostic(shift_x_px=20), self.diagnostic(shift_y_px=20))))

    def test_explicit_failure_survives_aggregation(self):
        self.assertFalse(_registration_is_valid(self.aggregate(
            self.diagnostic(), self.diagnostic(passed=False, failure_reason='motion'))))

    def test_missing_diagnostic_cannot_be_hidden_by_first_frame(self):
        self.assertFalse(_registration_is_valid(self.aggregate(self.diagnostic(), {})))

    def test_each_frame_uses_its_own_scale(self):
        self.assertTrue(_registration_is_valid(self.aggregate(
            self.diagnostic(shift_x_px=40, long_edge_px=1024), self.diagnostic())))


class TestReplay(unittest.TestCase):
    def test_real_runner_output_replays_without_inventing_semantic_evidence(self):
        from tests.test_nare_runner import _row
        from hybrid_engine.evaluation.nare_runner import run_nare_metrics
        from hybrid_engine.evaluation.nare_cli import build_report
        from hybrid_engine.evaluation.evidence_receipt import build_receipt, sign_receipt
        from brands.fuji import apply_provia
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = [_row(tmp)]
            image = np.random.default_rng(42).integers(20, 230, (64, 64, 3), dtype=np.uint8)
            # Only file decoding is replaced; registration, colour metrics,
            # candidate, receipt checks and report evaluation all run for real.
            with patch('hybrid_engine.evaluation.nare_runner.load_neutral_render', return_value=image), \
                 patch('hybrid_engine.evaluation.nare_runner.cv2.imread', return_value=image):
                metrics = run_nare_metrics(manifest, 'F0/Standard (Provia)', candidate=apply_provia)
                paths = {}
                for name, value in dict(manifest=manifest, metrics=metrics, controls={}).items():
                    paths[name] = root / (name + '.json')
                    paths[name].write_text(json.dumps(value))
                key = Ed25519PrivateKey.generate()
                pub = root / 'public.key'
                pub.write_text(base64.b64encode(key.public_key().public_bytes_raw()).decode())
                receipt = sign_receipt(build_receipt(paths, git_sha='a'*40,
                    evaluator_sha256='b'*64, command=['recorded'], run_id='real-test',
                    timestamp='test', run_config={'bootstrap':100,'seed':0},
                    required_artifacts=tuple(paths)), key, key_id='local')
                rp = root / 'receipt.json'
                rp.write_text(json.dumps(receipt))
                report = build_report(*(str(paths[k]) for k in ('manifest','metrics','controls')),
                    n_bootstrap=100, receipt_path=str(rp), receipt_public_key_path=str(pub),
                    expected_git_sha='a'*40)
            self.assertTrue(report['evidence_receipt']['replay_passed'])
            self.assertFalse(report['paired']['subgroup_metrics_passed'])
            self.assertEqual(report['classification']['classification'], 'Inconclusive')

    def replay(self, submitted, replayed):
        from hybrid_engine.evaluation.nare_replay import replay_metrics
        with patch('hybrid_engine.evaluation.nare_runner.run_nare_metrics', return_value=replayed):
            return replay_metrics([], submitted)

    def test_fabricated_numbers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'replay'):
            self.replay([{'scene_id': 's', 'raw_delta_e00': 100}],
                        [{'scene_id': 's', 'raw_delta_e00': 10}])

    def test_invented_semantic_metrics_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'replay'):
            self.replay([{'scene_id': 's', 'subgroups': {'skin': {}}}], [{'scene_id': 's'}])

    def test_matching_metrics_return_recomputed_records(self):
        rows = [{'scene_id': 's', 'raw_delta_e00': 10.}]
        self.assertEqual(self.replay(list(rows), rows), rows)

    def test_scene_order_does_not_change_replay(self):
        rows = [{'scene_id': 'a'}, {'scene_id': 'b'}]
        self.assertEqual(self.replay(rows[::-1], rows), rows)
