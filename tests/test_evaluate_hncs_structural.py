import contextlib
import io
import unittest

import numpy as np

from tools.evaluate_hncs_structural import (
    _sign_test_p, classify_illuminant_cluster, compute_blend_weight_rb,
    fit_color_matrix, apply_color_matrix, make_folds, summarize,
)

# 이 파일은 예전에 원본 13쌍(X1D 전용) 실험판 tools/evaluate_hncs_structural.py를
# 대상으로 `_pair_names`/`_resize_max_dim`을 테스트했는데, 그 사이 모듈이
# dpreview 95쌍(4세대) 5-fold 재실험판으로 전면 재작성되면서 `_pair_names`가
# 아예 없어져 import 자체가 깨졌다(CI에서 발견, 2026-08-09). RAW_DIR도
# 로컬 하드코딩 절대경로(`/Users/songjiun/...`)라 `load_pairs()`/`run_kfold()`
# 자체가 CI는 물론 이 컨테이너에서도 못 돈다 - tests/CLAUDE.md의 "CI has
# no image data" 원칙대로 raw 디코드가 필요 없는 순수 함수만 골라 다시
# 테스트한다. 이 모듈의 `summarize()`는 dict를 반환하지 않고 결과를
# 표준출력에 찍기만 하므로(다른 evaluate_*.py의 `summarize()`와 인터페이스가
# 다르다), `TestSummarizeRecordedRun` 패턴 대신 출력 캡처로 스모크테스트한다.


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(6, 6), 1.0)

    def test_no_pairs_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(0, 0), 1.0)

    def test_all_wins_is_significant(self):
        self.assertLess(_sign_test_p(13, 0), 0.001)

    def test_known_exact_value(self):
        # 다른 evaluate_*.py들의 동일 구현/동일 관례로 교차검증한 값
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


class TestSummarizePrintsVerdict(unittest.TestCase):
    """summarize()는 dict를 반환하지 않고 표준출력에만 판정을 찍는다
    (위 모듈독스트링 참고). 고정 시드로 재현 가능한 값을 찍는지만
    스모크테스트한다."""

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
        self.assertIn("판정: 구조실험 우세", out)


if __name__ == "__main__":
    unittest.main()
