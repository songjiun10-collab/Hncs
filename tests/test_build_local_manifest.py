import csv
import os
import random
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from tools.build_local_manifest import RAW_EXT, _match_pairs, drop_failed


class TestRawExt(unittest.TestCase):
    def test_covers_hasselblad_and_leica(self):
        self.assertIn(".3fr", RAW_EXT)
        self.assertIn(".fff", RAW_EXT)
        self.assertIn(".dng", RAW_EXT)


def _rec(filename, dt):
    return dict(filename=filename, dt=dt, model="Hasselblad X1D", lens="XCD 45", iso="100")


class TestMatchPairsDeterminism(unittest.TestCase):
    """_match_pairs()가 입력 순서(옛 구현에서는 사실상 os.listdir() 순서)와
    무관하게 항상 같은 결과를 내는지 확인 - 이게 이번 정정의 핵심 요구."""

    def _assert_order_invariant(self, raws, jpegs, expected_pairs):
        """raws/jpegs를 여러 순서로 섞어 넣어도 매번 같은 (raw, jpeg)
        페어링이 나오는지 확인. expected_pairs: {raw_filename: jpeg_filename}."""
        rng = random.Random(0)
        for trial in range(5):
            shuffled_raws = list(raws)
            shuffled_jpegs = list(jpegs)
            rng.shuffle(shuffled_raws)
            rng.shuffle(shuffled_jpegs)
            result = _match_pairs(shuffled_raws, shuffled_jpegs)
            actual = {r["filename"]: j["filename"] for r, j, _, _, _ in result}
            self.assertEqual(actual, expected_pairs, f"trial {trial}: 입력 순서를 바꾸니 매칭이 달라짐")

    def test_same_timestamp_both_sides_tied_is_flagged_ambiguous(self):
        """raw 둘, jpeg 둘이 전부 완전히 같은 초에 찍힘(카메라의 EXIF
        타임스탬프 해상도가 초 단위라 버스트에서 흔함) - (0001,0001)+
        (0002,0002)든 (0001,0002)+(0002,0001)이든 총비용이 똑같아서
        어느 쪽이 "진짜"인지 시간만으로는 알 수 없다. 조용히 아무거나
        골라 확정하면 안 되고 is_ambiguous=True로 표시해야 한다(모든 raw/
        jpeg가 어쨌든 정확히 한 번씩만 쓰이는 진짜 1:1인지는 계속 확인)."""
        t = datetime(2026, 8, 1, 12, 0, 0)
        raws = [_rec("IMG_0001.3fr", t), _rec("IMG_0002.3fr", t)]
        jpegs = [_rec("IMG_0001.jpg", t), _rec("IMG_0002.jpg", t)]
        result = _match_pairs(raws, jpegs)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(is_ambiguous for *_, is_ambiguous in result),
                         "동률 매칭인데 ambiguous로 표시가 안 됨")
        raw_used = {r["filename"] for r, j, d, oh, amb in result}
        jpeg_used = {j["filename"] for r, j, d, oh, amb in result}
        self.assertEqual(raw_used, {"IMG_0001.3fr", "IMG_0002.3fr"})
        self.assertEqual(jpeg_used, {"IMG_0001.jpg", "IMG_0002.jpg"})

    def test_burst_picks_closest_not_first_encountered(self):
        """1초 간격 버스트 3장 - 옛 구현은 raw를 시각순으로 처리하며
        "그 순간 풀에 남아있는 첫 매치"를 집어서, jpeg 풀의 순서가
        어긋나 있으면(예: 파일시스템이 j3/j1/j2 순으로 나열) 엉뚱하게
        섞일 수 있었다(r1-j2 delta=1s도 2초 문턱 안에 들어오므로). 새
        구현은 델타 오름차순(전부 delta=0인 정확한 매치가 먼저 확정)이라
        입력 순서와 무관하게 항상 정확히 매칭돼야 한다."""
        raws = [
            _rec("R1.3fr", datetime(2026, 8, 1, 12, 0, 0)),
            _rec("R2.3fr", datetime(2026, 8, 1, 12, 0, 1)),
            _rec("R3.3fr", datetime(2026, 8, 1, 12, 0, 2)),
        ]
        jpegs = [
            _rec("J1.jpg", datetime(2026, 8, 1, 12, 0, 0)),
            _rec("J2.jpg", datetime(2026, 8, 1, 12, 0, 1)),
            _rec("J3.jpg", datetime(2026, 8, 1, 12, 0, 2)),
        ]
        expected = {"R1.3fr": "J1.jpg", "R2.3fr": "J2.jpg", "R3.3fr": "J3.jpg"}
        self._assert_order_invariant(raws, jpegs, expected)

    def test_multiple_raw_for_one_jpeg_picks_closest_leaves_other_unmatched(self):
        """브라켓 촬영 등으로 raw 두 장이 후보에 몰렸는데 jpeg는 한 장뿐인
        경우 - 더 가까운 raw만 매칭되고 나머지 raw는 짝 없이 남아야
        한다(강제로 아무 raw에나 붙이면 안 됨)."""
        raws = [
            _rec("CLOSE.3fr", datetime(2026, 8, 1, 12, 0, 0, 500000)),
            _rec("FAR.3fr", datetime(2026, 8, 1, 12, 0, 1, 800000)),
        ]
        jpegs = [_rec("ONLY.jpg", datetime(2026, 8, 1, 12, 0, 0))]
        result = _match_pairs(raws, jpegs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0]["filename"], "CLOSE.3fr")
        self.assertEqual(result[0][1]["filename"], "ONLY.jpg")

    def test_multiple_jpeg_for_one_raw_picks_closest_leaves_other_unmatched(self):
        """raw 한 장에 jpeg 두 장이 후보로 몰린 경우(예: 원본 + 사본
        JPEG) - 더 가까운 jpeg만 매칭되고 나머지는 짝 없이 남아야 한다."""
        raws = [_rec("ONLY.3fr", datetime(2026, 8, 1, 12, 0, 0))]
        jpegs = [
            _rec("CLOSE.jpg", datetime(2026, 8, 1, 12, 0, 0, 300000)),
            _rec("FAR.jpg", datetime(2026, 8, 1, 12, 0, 1, 900000)),
        ]
        result = _match_pairs(raws, jpegs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0]["filename"], "ONLY.3fr")
        self.assertEqual(result[0][1]["filename"], "CLOSE.jpg")

    def test_global_assignment_beats_greedy_nearest_first(self):
        """그리디(델타 오름차순으로 하나씩 확정)와 전역 최적(헝가리안)이
        실제로 다른 결과를 내는 구체적 사례 - 그리디는 R1을 가장 가까운
        J1에 먼저 확정시켜버려서 R2가 갈 곳이 없어진다(R2-J2는 2초
        문턱을 넘어 애초에 후보가 아님). 전역 최적은 R1을 차선책(J2)으로
        보내고 J1을 R2에게 양보해서 둘 다 매칭시키는 게 총비용상 더
        낫다는 걸 안다 - 매칭 개수 자체가 그리디(1쌍)보다 전역 최적
        (2쌍)이 많다."""
        t0 = datetime(2026, 8, 1, 12, 0, 0)
        raws = [
            _rec("R1.3fr", t0),
            _rec("R2.3fr", t0 - timedelta(seconds=0.3)),
        ]
        jpegs = [
            _rec("J1.jpg", t0 + timedelta(seconds=1.0)),  # R1-J1=1.0s, R2-J1=1.3s
            _rec("J2.jpg", t0 + timedelta(seconds=1.8)),  # R1-J2=1.8s, R2-J2=2.1s(문턱 밖)
        ]
        result = _match_pairs(raws, jpegs)
        self.assertEqual(len(result), 2, "전역 최적이면 둘 다 매칭돼야 함(그리디는 1쌍만 매칭)")
        actual = {r["filename"]: j["filename"] for r, j, _, _, _ in result}
        self.assertEqual(actual, {"R1.3fr": "J2.jpg", "R2.3fr": "J1.jpg"})

    def test_zero_offset_preferred_over_smaller_delta_at_nonzero_offset(self):
        """정수시간 오프셋 카메라(2017 X1D 사례, 파일 docstring 참고) 지원과
        "같은 초 매치가 있으면 그게 진짜"라는 기존 설계를 유지하는지 확인 -
        raw 한 장에 jpeg 후보가 둘: J_ZERO는 offset=0에서 델타 1.9초로
        맞고, J_OFFSET은 offset=+1h에서 델타 0.1초로(수치상 더 가까움)
        맞는다 - 그래도 offset=0 쪽(J_ZERO)을 우선해야 한다."""
        raws = [_rec("R.3fr", datetime(2026, 8, 1, 12, 0, 0))]
        jpegs = [
            _rec("J_ZERO.jpg", datetime(2026, 8, 1, 12, 0, 1, 900000)),  # delta=1.9s, offset=0
            _rec("J_OFFSET.jpg", datetime(2026, 8, 1, 13, 0, 0, 100000)),  # delta=0.1s, offset=+1h
        ]
        result = _match_pairs(raws, jpegs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1]["filename"], "J_ZERO.jpg")
        self.assertEqual(result[0][3], 0)  # offset_h


def _fake_verify_row(set_dir, row, expected_make="Hasselblad"):
    return [] if row["filename_raw"] == "PASS.3fr" else ["fake problem"]


class TestDropFailedDoesNotDeleteFiles(unittest.TestCase):
    """append_manifest()가 원본을 src_dir에서 move()해오므로, 검증 실패
    파일을 drop_failed()가 os.remove()로 영구 삭제하면 유일한 사본이
    사라진다(리뷰에서 지적된 데이터 유실 위험). rejected/로 옮겨서
    복구 가능해야 한다.

    verify_row()는 실제로는 tools.verify_contributed_pairs를 통해
    tools.analyze -> tools.download -> gdown으로 이어지는 무거운 의존성
    체인을 끌고 오는데, 이 샌드박스엔 gdown이 없다(tests/CLAUDE.md
    "CI has no image data"). drop_failed()는 이 모듈을 함수 안에서
    지연 import하므로, sys.modules에 가짜 모듈을 미리 심어두면 실제
    import가 실행되지 않고 이 스텁이 대신 쓰인다."""

    def setUp(self):
        self._sys_modules_patch = patch.dict(sys.modules, {
            "tools.verify_contributed_pairs": types.SimpleNamespace(
                verify_row=_fake_verify_row),
        })
        self._sys_modules_patch.start()

        self.set_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.set_dir, "raw"))
        os.makedirs(os.path.join(self.set_dir, "jpeg"))
        for sub, name, content in (
            ("raw", "PASS.3fr", b"raw-pass"),
            ("jpeg", "PASS.jpg", b"jpeg-pass"),
            ("raw", "FAIL.3fr", b"raw-fail"),
            ("jpeg", "FAIL.jpg", b"jpeg-fail"),
        ):
            with open(os.path.join(self.set_dir, sub, name), "wb") as f:
                f.write(content)
        with open(os.path.join(self.set_dir, "manifest.csv"), "w", newline="") as f:
            fieldnames = ["filename_raw", "filename_jpeg", "camera", "lens", "iso",
                          "wb_setting", "scene_type", "filename_phocus_tiff",
                          "phocus_settings", "illuminant", "download_url", "notes"]
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for raw, jpeg in (("PASS.3fr", "PASS.jpg"), ("FAIL.3fr", "FAIL.jpg")):
                w.writerow({k: "" for k in fieldnames} | dict(
                    filename_raw=raw, filename_jpeg=jpeg))

    def tearDown(self):
        self._sys_modules_patch.stop()
        shutil.rmtree(self.set_dir, ignore_errors=True)

    def test_failed_files_moved_to_rejected_not_deleted(self):
        drop_failed(self.set_dir)

        self.assertTrue(os.path.exists(
            os.path.join(self.set_dir, "raw", "PASS.3fr")))
        self.assertFalse(os.path.exists(
            os.path.join(self.set_dir, "raw", "FAIL.3fr")))
        self.assertTrue(os.path.exists(
            os.path.join(self.set_dir, "rejected", "raw", "FAIL.3fr")))
        self.assertTrue(os.path.exists(
            os.path.join(self.set_dir, "rejected", "jpeg", "FAIL.jpg")))
        with open(os.path.join(self.set_dir, "rejected", "raw", "FAIL.3fr"), "rb") as f:
            self.assertEqual(f.read(), b"raw-fail")


if __name__ == "__main__":
    unittest.main()
