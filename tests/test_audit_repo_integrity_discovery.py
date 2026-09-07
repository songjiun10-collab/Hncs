"""`tools/maintenance/audit_repo_integrity.py`의 코드 discovery가 조용히
0개를 찾고 "이상 없음"으로 통과하는 걸 막는 회귀 테스트.

이 클래스의 버그가 실제로 두 번 있었다:
1. `brands/`가 브랜드별 패키지로 나뉜 뒤(`brands/hasselblad/look.py` 등)
   `os.listdir()` 한 단계짜리 discovery가 브랜드 파일을 하나도 못 찾았다.
2. 위를 "한 단계 하위까지"로 고쳤는데, 2026-09-06에 `tools/`도
   `tools/data/verify_contributed_pairs.py`처럼 서브패키지로 나뉘면서 같은
   한계(두 단계 이상은 못 봄)를 다시 안고 있었다 - 이번엔 실제로 2단계
   이상 깊은 파일이 없어서 터지지 않았을 뿐이다.

`_code_files()`를 `os.walk` 기반 완전 재귀로 바꾸고,
`check_registration()`이 어느 CODE_DIRS든 0개를 찾으면 그 자체를
이상으로 보고하게 했다 - 여기서는 그 둘을 각각 확인한다.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from tools.maintenance.audit_repo_integrity import CODE_DIRS, _code_files, check_registration


class TestCodeFilesRecursion(unittest.TestCase):
    """`_code_files()`가 임의 깊이까지 재귀하는지 - 실제로 벌어졌던 두
    사건(1단계, 2단계 파일 누락)을 둘 다 커버하는 디렉토리 구조로 확인."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        os.makedirs(os.path.join(root, "sub", "deeper"))
        os.makedirs(os.path.join(root, "__pycache__"))
        os.makedirs(os.path.join(root, ".hidden"))
        for rel in ("top.py", "__init__.py",
                    "sub/one_level.py", "sub/__init__.py",
                    "sub/deeper/two_levels.py",
                    "__pycache__/cached.py", ".hidden/dotfile.py"):
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").close()
        self.root = root

    def test_finds_top_level_file(self):
        self.assertIn("top.py", _code_files(self.root))

    def test_finds_one_level_deep_file(self):
        self.assertIn("sub/one_level.py", _code_files(self.root))

    def test_finds_two_levels_deep_file(self):
        # 이게 2026-09-06 사건의 정확한 재현 - 고치기 전엔 여기서 실패했다.
        self.assertIn("sub/deeper/two_levels.py", _code_files(self.root))

    def test_excludes_init_and_pycache_and_hidden_dirs(self):
        found = _code_files(self.root)
        self.assertNotIn("__init__.py", found)
        self.assertNotIn("sub/__init__.py", found)
        self.assertFalse(any("__pycache__" in f for f in found))
        self.assertFalse(any(".hidden" in f for f in found))


class TestCheckRegistrationCatchesEmptyDiscovery(unittest.TestCase):
    """discovery가 0개를 찾으면 등재 누락이 아니라 그 사실 자체가 이상으로
    보고돼야 한다 - 안 그러면 "발견 0개 = 이상 없음"이 된다."""

    def test_zero_files_in_any_code_dir_is_reported_as_a_problem(self):
        with patch("tools.maintenance.audit_repo_integrity._code_files",
                   return_value=[]):
            problems = check_registration()
        for d in CODE_DIRS:
            self.assertTrue(
                any(f"{d}/에서" in p and "discovery" in p for p in problems),
                f"{d}/ discovery가 0개일 때 문제로 보고되지 않음: {problems}")

    def test_real_code_dirs_each_yield_at_least_one_file(self):
        """모킹 없이 실제 저장소 상태로 - 지금 이 순간 discovery가 살아있는지."""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for d in CODE_DIRS:
            with self.subTest(dir=d):
                self.assertGreater(len(_code_files(os.path.join(base, d))), 0,
                                   f"{d}/에서 실제로 0개 발견 - discovery 회귀")


if __name__ == "__main__":
    unittest.main()
