import unittest

import numpy as np

from hybrid_engine.core.raw_baseline import (
    fit_color_matrix, apply_color_matrix, root_polynomial_features,
)


class TestFitColorMatrix(unittest.TestCase):
    def test_identity_when_targets_equal_sources(self):
        rng = np.random.default_rng(0)
        img = rng.uniform(0.05, 0.9, size=(20, 20, 3))
        matrix = fit_color_matrix([img], [img])
        np.testing.assert_allclose(matrix, np.eye(3), atol=1e-6)

    def test_recovers_known_linear_transform(self):
        rng = np.random.default_rng(1)
        img = rng.uniform(0.05, 0.9, size=(30, 30, 3))
        known_matrix = np.array([
            [1.1, 0.05, -0.02],
            [0.02, 0.95, 0.01],
            [-0.01, 0.03, 1.2],
        ])
        target = img @ known_matrix
        fitted = fit_color_matrix([img], [target])
        np.testing.assert_allclose(fitted, known_matrix, atol=1e-6)

    def test_multiple_pairs_are_pooled(self):
        rng = np.random.default_rng(2)
        known_matrix = np.array([[1.2, 0.0, 0.0], [0.0, 0.9, 0.0], [0.0, 0.0, 1.0]])
        imgs = [rng.uniform(0.05, 0.9, size=(10, 10, 3)) for _ in range(3)]
        targets = [img @ known_matrix for img in imgs]
        fitted = fit_color_matrix(imgs, targets)
        np.testing.assert_allclose(fitted, known_matrix, atol=1e-6)


class TestApplyColorMatrix(unittest.TestCase):
    def test_shape_preserved(self):
        rng = np.random.default_rng(3)
        img = rng.uniform(0.05, 0.9, size=(12, 14, 3))
        out = apply_color_matrix(img, np.eye(3))
        self.assertEqual(out.shape, img.shape)

    def test_identity_matrix_is_noop(self):
        rng = np.random.default_rng(4)
        img = rng.uniform(0.05, 0.9, size=(8, 8, 3))
        out = apply_color_matrix(img, np.eye(3))
        np.testing.assert_allclose(out, img, atol=1e-10)

    def test_negative_results_are_clipped(self):
        img = np.full((4, 4, 3), 0.1)
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-5.0, 0.0, 1.0]])
        out = apply_color_matrix(img, matrix)
        self.assertTrue(np.all(out >= 0.0))


class TestRootPolynomialFeatures(unittest.TestCase):
    def test_output_shape(self):
        rng = np.random.default_rng(10)
        img = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        feats = root_polynomial_features(img)
        self.assertEqual(feats.shape, (6, 6, 6))

    def test_known_pixel_values(self):
        img = np.array([[[0.4, 0.9, 0.25]]])
        feats = root_polynomial_features(img)
        expected = np.array([[[0.4, 0.9, 0.25,
                                np.sqrt(0.4 * 0.9),
                                np.sqrt(0.4 * 0.25),
                                np.sqrt(0.9 * 0.25)]]])
        np.testing.assert_allclose(feats, expected, atol=1e-10)

    def test_exposure_invariance_of_fitted_matrix_prediction(self):
        # 노출(전역 밝기 스케일)이 k배 바뀌어도 같은 매트릭스로 예측한 결과이
        # 그대로 k배가 되어야 한다 - root-polynomial의 핵심 성질(노출 불변).
        rng = np.random.default_rng(11)
        img = rng.uniform(0.05, 0.6, size=(10, 10, 3))
        matrix = rng.uniform(-0.2, 1.2, size=(6, 3))
        pred = root_polynomial_features(img).reshape(-1, 6) @ matrix

        k = 2.5
        scaled_pred = root_polynomial_features(img * k).reshape(-1, 6) @ matrix
        np.testing.assert_allclose(scaled_pred, pred * k, rtol=1e-8)


class TestFitColorMatrixWithFeatureFn(unittest.TestCase):
    def test_root_polynomial_recovers_known_matrix(self):
        rng = np.random.default_rng(12)
        img = rng.uniform(0.05, 0.9, size=(30, 30, 3))
        known_matrix = rng.uniform(-0.3, 1.3, size=(6, 3))
        target = (root_polynomial_features(img).reshape(-1, 6) @ known_matrix).reshape(img.shape)

        fitted = fit_color_matrix([img], [target], feature_fn=root_polynomial_features)
        np.testing.assert_allclose(fitted, known_matrix, atol=1e-6)


class TestFitColorMatrixWeighted(unittest.TestCase):
    def test_weighted_matches_manual_weighted_lstsq(self):
        rng = np.random.default_rng(14)
        img = rng.uniform(0.05, 0.9, size=(5, 5, 3))
        target = rng.uniform(0.05, 0.9, size=(5, 5, 3))
        w = rng.uniform(0.1, 2.0, size=(5, 5))

        fitted = fit_color_matrix([img], [target], weights=[w])

        X = img.reshape(-1, 3)
        Y = target.reshape(-1, 3)
        sw = np.sqrt(w.reshape(-1))[:, None]
        expected, _, _, _ = np.linalg.lstsq(X * sw, Y * sw, rcond=None)
        np.testing.assert_allclose(fitted, expected, atol=1e-8)

    def test_uniform_weights_match_unweighted(self):
        rng = np.random.default_rng(15)
        img = rng.uniform(0.05, 0.9, size=(10, 10, 3))
        target = rng.uniform(0.05, 0.9, size=(10, 10, 3))
        w = np.ones((10, 10))
        weighted = fit_color_matrix([img], [target], weights=[w])
        unweighted = fit_color_matrix([img], [target])
        np.testing.assert_allclose(weighted, unweighted, atol=1e-8)


class TestFitColorMatrixRidge(unittest.TestCase):
    def test_higher_ridge_shrinks_matrix_norm(self):
        rng = np.random.default_rng(16)
        img = rng.uniform(0.05, 0.9, size=(15, 15, 3))
        target = rng.uniform(0.05, 0.9, size=(15, 15, 3))
        m0 = fit_color_matrix([img], [target], ridge=0.0)
        m1 = fit_color_matrix([img], [target], ridge=1.0)
        self.assertLess(np.linalg.norm(m1), np.linalg.norm(m0))


class TestApplyColorMatrixWithFeatureFn(unittest.TestCase):
    def test_root_polynomial_apply_matches_manual(self):
        rng = np.random.default_rng(17)
        img = rng.uniform(0.05, 0.9, size=(4, 4, 3))
        matrix = rng.uniform(-0.5, 1.5, size=(6, 3))
        out = apply_color_matrix(img, matrix, feature_fn=root_polynomial_features)
        expected = np.clip(
            root_polynomial_features(img).reshape(-1, 6) @ matrix, 0.0, None
        ).reshape(img.shape)
        np.testing.assert_allclose(out, expected, atol=1e-10)


if __name__ == "__main__":
    unittest.main()
