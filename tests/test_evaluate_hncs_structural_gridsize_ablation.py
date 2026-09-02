"""`tools/evaluate_hncs_structural_gridsize_ablation.py`의 순수 함수
테스트 - raw 디코드가 필요한 load_pairs()/run_kfold()는 CI에 이미지
데이터가 없어서 제외한다(tests/CLAUDE.md). 이 파일의 모든 함수는
evaluate_hncs_structural.py와 코드가 100% 동일(그리드 크기만 다름,
그리드 크기는 이 함수들에 영향 없음)이라
tests/test_evaluate_hncs_structural.py의 대응 테스트를 그대로
가져왔다 - 어느 한쪽 원본이 바뀌면 그 동일성 전제가 깨졌다는 뜻이니
두 테스트 파일이 같이 관리돼야 한다."""
import contextlib
import io
import unittest

import numpy as np

from tools.evaluate_hncs_structural_gridsize_ablation import (
    _sign_test_p, classify_illuminant_cluster, compute_blend_weight_rb,
    fit_color_matrix, apply_color_matrix, make_folds, summarize,
    CHROMA_COMBOS,
)


class TestGridSize(unittest.TestCase):
    def test_grid_is_256_not_1024(self):
        """이 스크립트의 유일한 존재 이유 - 16x16=256이어야 한다."""
        self.assertEqual(len(CHROMA_COMBOS), 256)


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(6, 6), 1.0)

    def test_no_pairs_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(0, 0), 1.0)

    def test_all_wins_is_significant(self):
        self.assertLess(_sign_test_p(13, 0), 0.001)

    def test_known_exact_value(self):
        self.assertAlmostEqual(_sign_test_p(10, 3), 0.09228515625, places=9)


class TestClassifyIlluminantCluster(unittest.TestCase):
    def test_below_threshold_is_cluster_a(self):
        self.assertEqual(classify_illuminant_cluster(np.array([0.89, 1.0, 1.0])), "cluster_a")

    def test_at_or_above_threshold_is_cluster_b(self):
        self.assertEqual(classify_illuminant_cluster(np.array([0.9, 1.0, 1.0])), "cluster_b")
        self.assertEqual(classify_illuminant_cluster(np.array([1.2, 1.0, 1.0])), "cluster_b")

    def test_custom_threshold(self):
        self.assertEqual(
            classify_illuminant_cluster(np.array([0.5, 1.0, 1.0]), threshold=0.4), "cluster_b")


class TestFitColorMatrixRoundTrip(unittest.TestCase):
    def test_recovers_known_linear_transform(self):
        rng = np.random.default_rng(0)
        true_matrix = np.array([[1.1, 0.0, 0.0], [0.0, 0.9, 0.05], [0.0, 0.0, 1.0]])
        source = rng.uniform(0, 1, size=(50, 50, 3))
        target = source @ true_matrix
        fitted = fit_color_matrix([source], [target], ridge=0.0)
        np.testing.assert_allclose(fitted, true_matrix, atol=1e-6)

    def test_apply_color_matrix_reproduces_target(self):
        rng = np.random.default_rng(1)
        true_matrix = np.array([[1.0, 0.1, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.95]])
        source = rng.uniform(0, 1, size=(20, 20, 3))
        target = source @ true_matrix
        fitted = fit_color_matrix([source], [target], ridge=0.0)
        out = apply_color_matrix(source, fitted)
        np.testing.assert_allclose(out, target, atol=1e-6)

    def test_clips_negative_output(self):
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]])
        rgb = np.ones((2, 2, 3))
        out = apply_color_matrix(rgb, matrix)
        self.assertTrue((out >= 0.0).all())


class TestComputeBlendWeightRb(unittest.TestCase):
    def test_weight_zero_at_rb_min(self):
        self.assertAlmostEqual(compute_blend_weight_rb(np.array([0.8, 1.0, 1.0]), 0.8, 1.0), 0.0)

    def test_weight_one_at_rb_max(self):
        self.assertAlmostEqual(compute_blend_weight_rb(np.array([1.0, 1.0, 1.0]), 0.8, 1.0), 1.0)

    def test_weight_interpolates_linearly(self):
        self.assertAlmostEqual(compute_blend_weight_rb(np.array([0.9, 1.0, 1.0]), 0.8, 1.0), 0.5)

    def test_degenerate_range_returns_half(self):
        self.assertAlmostEqual(compute_blend_weight_rb(np.array([1.0, 1.0, 1.0]), 1.0, 1.0), 0.5)


class TestMakeFolds(unittest.TestCase):
    def test_folds_partition_all_indices_exactly_once(self):
        pairs = list(range(10))
        folds = make_folds(pairs, n_folds=3, seed=0)
        self.assertEqual(len(folds), 3)
        covered = sorted(np.concatenate(folds).tolist())
        self.assertEqual(covered, list(range(10)))

    def test_deterministic_given_same_seed(self):
        pairs = list(range(13))
        folds_a = make_folds(pairs, n_folds=5, seed=0)
        folds_b = make_folds(pairs, n_folds=5, seed=0)
        for a, b in zip(folds_a, folds_b):
            np.testing.assert_array_equal(a, b)

    def test_matches_original_script_fold_split(self):
        """이 스크립트는 evaluate_hncs_structural.py와 정확히 같은
        폴드 분할이어야 한다(그리드 크기만 격리하려는 게 목적이므로) -
        같은 make_folds 구현 + 같은 seed=0이면 같은 입력에 항상 같은
        출력이 나오는 걸 원본 모듈과 교차확인."""
        from tools.evaluate_hncs_structural import make_folds as original_make_folds
        pairs = list(range(389))
        a = make_folds(pairs, n_folds=5, seed=0)
        b = original_make_folds(pairs, n_folds=5, seed=0)
        for fa, fb in zip(a, b):
            np.testing.assert_array_equal(fa, fb)


class TestSummarizePrintsVerdict(unittest.TestCase):
    def _run(self, hncs_des, other_des, label):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            summarize(hncs_des, other_des, label, n_bootstrap=2000, seed=0)
        return buf.getvalue()

    def test_reports_means_and_win_count(self):
        out = self._run([10.0, 12.0, 9.0, 11.0], [8.0, 12.5, 7.5, 10.5], "test-label")
        self.assertIn("평균 apply_hncs ΔE00=10.500", out)
        self.assertIn("평균 test-label ΔE00=9.625", out)
        self.assertIn("승/패=3/1", out)

    def test_inconclusive_verdict_when_ci_straddles_zero(self):
        out = self._run([10.0, 12.0, 9.0, 11.0], [8.0, 12.5, 7.5, 10.5], "test-label")
        self.assertIn("판정: 보류", out)

    def test_decisive_verdict_when_all_folds_agree(self):
        out = self._run([10.0, 12.0, 9.0, 11.0], [8.0, 9.0, 7.0, 8.0], "test-label")
        self.assertIn("판정: test-label 우세", out)


if __name__ == "__main__":
    unittest.main()
