"""
`brands/*.py`의 `apply_*()` 룩을 캡처원 DeviceLink ICC(`.icc`,
lut8Type/'mft1')로 굽는다 - 캡처원이 `.cube`를 아예 지원 안 해서
(2026-09-02 조사, "using LUT (3dl, cube etc..)" 캡처원 공식 커뮤니티
답변) 만든 대안 경로. `core.lut_export.bake_lut_from_function()`으로
이미 검증된 방식(CLAHE 등 적응형 연산을 합성 이미지 하나로 한 번에
통과시킴)으로 격자를 굽고, `core.icc_export.write_icc_devicelink_look_from_lut()`
로 파일만 다른 포맷으로 낸다 - 새 굽기 로직 없음.

**한계**: CLAHE는 점별 매핑으로 못 담아서(`.cube`와 동일 한계) 실사진
기준 평균 절대오차 ΔBGR≈21/255(하셀블라드 챠트 프레임 실측, 최근접
보간) 정도의 근사 오차가 있다 - 버그가 아니라 LUT 포맷 자체의 구조적
한계. 캡처원 실기기 미검증(exiftool/littlecms 구조 검증만).

  python3 -m tools.build_devicelink_icc_for_look <module> <func> <output.icc> <description>
  예: python3 -m tools.build_devicelink_icc_for_look brands.fuji apply_provia \
      hybrid_engine/assets/profiles/fuji_provia_look.icc "HNCS Fuji Provia Look"
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.icc_export import write_icc_devicelink_look_from_lut
from core.lut_export import bake_lut_from_function


def main():
    module_name, func_name, out_path, description = sys.argv[1:5]
    func = getattr(importlib.import_module(module_name), func_name)
    lut = bake_lut_from_function(func, size=33)
    write_icc_devicelink_look_from_lut(out_path, description, lut)
    print(f"발급: {out_path}")


if __name__ == "__main__":
    main()
