import unittest

from tools.build_local_manifest import RAW_EXT


class TestRawExt(unittest.TestCase):
    def test_covers_hasselblad_and_leica(self):
        self.assertIn(".3fr", RAW_EXT)
        self.assertIn(".fff", RAW_EXT)
        self.assertIn(".dng", RAW_EXT)


if __name__ == "__main__":
    unittest.main()
