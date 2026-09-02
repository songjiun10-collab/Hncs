"""`tools/fit_brand_matrix_chroma_pipeline.py`의 순수 부분만 검증 - RAW
디코드는 CI에 데이터가 없어서(tests/CLAUDE.md) 제외."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.fit_brand_matrix_chroma_pipeline import _sign_test_p, BRAND_CONFIG


class TestSignTestP(unittest.TestCase):
    def test_all_wins_gives_small_p(self):
        self.assertLess(_sign_test_p(10, 0), 0.01)

    def test_even_split_gives_p_near_one(self):
        self.assertGreater(_sign_test_p(5, 5), 0.9)

    def test_no_observations_returns_one(self):
        self.assertEqual(_sign_test_p(0, 0), 1.0)


class TestBrandConfig(unittest.TestCase):
    def test_configured_brands_import_cleanly(self):
        """BRAND_CONFIG에 등록된 (모듈, 함수명)이 실제로 존재하는지 -
        오타나 리네임으로 조용히 깨지는 걸 막는다."""
        import importlib
        for brand, (module_name, func_name, *_rest) in BRAND_CONFIG.items():
            mod = importlib.import_module(module_name)
            self.assertTrue(hasattr(mod, func_name),
                             f"{brand}: {module_name}.{func_name} 없음")


if __name__ == "__main__":
    unittest.main()
