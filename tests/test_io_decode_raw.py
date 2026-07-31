import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import rawpy

from hybrid_engine.utils.io import decode_raw


def _mock_raw_context(shape=(4, 4, 3)):
    mock_raw = MagicMock()
    mock_raw.postprocess.return_value = np.zeros(shape, dtype=np.uint16)
    mock_raw.__enter__.return_value = mock_raw
    mock_raw.__exit__.return_value = False
    return mock_raw


class TestDecodeRawDemosaicParam(unittest.TestCase):
    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_default_none_omits_demosaic_algorithm_kwarg(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw")

        _, kwargs = mock_raw.postprocess.call_args
        self.assertNotIn("demosaic_algorithm", kwargs)

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_explicit_algorithm_is_passed_through(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT)

        _, kwargs = mock_raw.postprocess.call_args
        self.assertEqual(kwargs["demosaic_algorithm"], rawpy.DemosaicAlgorithm.DHT)

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_other_kwargs_unchanged_by_new_parameter(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw")

        _, kwargs = mock_raw.postprocess.call_args
        self.assertTrue(kwargs["use_camera_wb"])
        self.assertTrue(kwargs["no_auto_bright"])
        self.assertEqual(kwargs["output_bps"], 16)
        self.assertEqual(kwargs["output_color"], rawpy.ColorSpace.sRGB)
        self.assertEqual(kwargs["gamma"], (1, 1))

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_return_value_still_normalized_to_unit_range(self, mock_imread):
        mock_raw = _mock_raw_context(shape=(2, 2, 3))
        mock_raw.postprocess.return_value = np.full((2, 2, 3), 65535, dtype=np.uint16)
        mock_imread.return_value = mock_raw

        result = decode_raw("fake.raw")

        self.assertEqual(result.dtype, np.float64)
        np.testing.assert_allclose(result, 1.0)


class TestDecodeRawChromaticAberrationParam(unittest.TestCase):
    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_default_none_omits_chromatic_aberration_kwarg(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw")

        _, kwargs = mock_raw.postprocess.call_args
        self.assertNotIn("chromatic_aberration", kwargs)

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_explicit_tuple_is_passed_through(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", chromatic_aberration=(1.01, 0.99))

        _, kwargs = mock_raw.postprocess.call_args
        self.assertEqual(kwargs["chromatic_aberration"], (1.01, 0.99))

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_both_new_params_can_be_combined(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT,
                    chromatic_aberration=(1.0, 1.02))

        _, kwargs = mock_raw.postprocess.call_args
        self.assertEqual(kwargs["demosaic_algorithm"], rawpy.DemosaicAlgorithm.DHT)
        self.assertEqual(kwargs["chromatic_aberration"], (1.0, 1.02))

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_other_kwargs_unchanged_by_new_parameter(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", chromatic_aberration=(1.01, 0.99))

        _, kwargs = mock_raw.postprocess.call_args
        self.assertTrue(kwargs["use_camera_wb"])
        self.assertTrue(kwargs["no_auto_bright"])
        self.assertEqual(kwargs["output_bps"], 16)
        self.assertEqual(kwargs["output_color"], rawpy.ColorSpace.sRGB)
        self.assertEqual(kwargs["gamma"], (1, 1))


if __name__ == "__main__":
    unittest.main()
