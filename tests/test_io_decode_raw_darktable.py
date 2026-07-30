import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from hybrid_engine.utils.io import decode_raw_darktable


def _nonblack_image(shape=(4, 4, 3)):
    """검은 행 비율 가드(black_row_fraction > 0.01)에 안 걸리는 목 이미지."""
    rng = np.random.default_rng(0)
    return rng.uniform(0.01, 1.0, size=shape).astype(np.float32)


class TestDecodeRawDarktable(unittest.TestCase):
    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_calls_darktable_cli_with_required_flags(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = _nonblack_image()

        decode_raw_darktable("fake.RAF")

        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "darktable-cli")
        self.assertEqual(cmd[1], "fake.RAF")
        self.assertIn("--icc-type", cmd)
        self.assertIn("LIN_REC709", cmd)
        self.assertIn("plugins/imageio/format/tiff/bpp=32", cmd)
        self.assertIn("plugins/darkroom/workflow=none", cmd)

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_subprocess_env_never_inherits_omp_num_threads(self, mock_run, mock_imread, mock_exists):
        """OMP_NUM_THREADS가 호출 프로세스 환경에 있어도 darktable-cli
        subprocess에는 절대 전달되면 안 된다 - 물려받으면 darktable이
        프레임 일부만 렌더링하고 나머지를 까맣게 남긴다(실측 확인,
        4코어 환경에서 OMP_NUM_THREADS=1이면 75% 잘림)."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = _nonblack_image()

        with patch.dict(os.environ, {"OMP_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1"}):
            decode_raw_darktable("fake.RAF")

        _, kwargs = mock_run.call_args
        self.assertIn("env", kwargs)
        self.assertNotIn("OMP_NUM_THREADS", kwargs["env"])
        self.assertNotIn("OMP_THREAD_LIMIT", kwargs["env"])

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_when_output_looks_truncated(self, mock_run, mock_imread, mock_exists):
        """행의 상당수가 완전히 검으면(전 채널 0) 잘린 렌더로 보고
        예외를 던진다 - 종료 코드/파일 존재만으로는 이 실패 모드를
        못 잡는다(darktable이 조용히 exit 0으로 끝냄, 실측 확인)."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        img = _nonblack_image(shape=(10, 4, 3))
        img[3:, :, :] = 0.0  # 70%가 완전히 검은 행
        mock_imread.return_value = img

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")

    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_on_nonzero_returncode(self, mock_run, mock_imread):
        mock_run.return_value = MagicMock(returncode=1, stderr="boom")

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")
        mock_imread.assert_not_called()

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=False)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_when_output_file_missing(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")
        mock_imread.assert_not_called()

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_when_imread_returns_none(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = None

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_negative_values_clipped_to_zero(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = np.array([[[-0.5, 0.2, 1.5]]], dtype=np.float32)

        result = decode_raw_darktable("fake.RAF")

        self.assertGreaterEqual(result.min(), 0.0)

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_bgr_converted_to_rgb(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # cv2 reads BGR order: blue=1.0, green=0.5, red=0.1
        mock_imread.return_value = np.array([[[1.0, 0.5, 0.1]]], dtype=np.float32)

        result = decode_raw_darktable("fake.RAF")

        # RGB order expected: red=0.1, green=0.5, blue=1.0
        np.testing.assert_allclose(result[0, 0], [0.1, 0.5, 1.0], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
