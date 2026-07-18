import unittest

import numpy as np

from hybrid_engine.core.raw_baseline import fit_color_matrix, apply_color_matrix


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


if __name__ == "__main__":
    unittest.main()
