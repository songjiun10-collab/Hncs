"""배포된 `brands/*.py`의 `apply_*` 룩 **전부**를 Capture One DeviceLink
ICC로 굽는다. 지금까지는 `tools/build_devicelink_icc_for_look.py`를 룩
하나씩 수동 호출했고, 그래서 41개 배포 룩 중 2개(하셀블라드 HNCS,
후지 Provia)만 캡처원 프로필이 있었다.

**왜 배치인가**: 룩이 늘어날 때마다 수동으로 한 줄씩 굽는 방식은
`tests/test_brands.py`의 수동 allowlist가 그랬듯 조용히 뒤처진다(실제로
2026-09에 그 allowlist에서 11개가 누락된 채 발견됐다). 이 스크립트는
룩 목록을 `tests/test_brands.py`에서 그대로 가져와 **테스트가 아는 룩과
캡처원 프로필이 항상 같은 집합**이 되게 한다.

**목록은 두 군데서 온다**: `BRAND_LOOKS`(자동 발견)는 `brands/fuji.py`를
통째로 제외하므로(fuji는 자체 `TestFujiPresets`가 완전성 검사를 한다)
`FUJI_COLOR_PRESETS`를 따로 합쳐야 한다. 이 스크립트 초판이 `BRAND_LOOKS`
만 써서 후지 필름시뮬레이션 13개가 전부 안 구워진 채 배포됐고,
2026-09-04에 커버리지를 세다가 발견했다 - "자동 발견을 재사용하니
안전하다"는 가정 자체가 그 자동 발견의 제외 목록까지 확인해야 성립한다는
사례.

**굽는 방식**: 새 로직 없음 - `core.lut_export.bake_lut_from_function()`
(합성 이미지 한 장을 통과시켜 격자를 얻는, 이미 검증된 방식)으로 33³
격자를 만들고 `core.icc_export.write_icc_devicelink_look_from_lut()`로
lut8Type('mft1') DeviceLink ICC를 쓴다. 캡처원이 `.cube`를 지원하지
않아 만든 경로다(`tools/build_devicelink_icc_for_look.py` 독스트링 참고).

**검증**: (1) 항등 검사 - LUT가 입력 격자와 같으면 굽기 실패이거나
무동작 룩이므로 제외한다. (2) **충실도 측정** - 랜덤 BGR 이미지를
LUT로 통과시킨 결과와 룩 함수를 직접 호출한 결과의 평균 절대오차
ΔBGR을, 그 룩이 원본 대비 만드는 변화량("룩 효과")과 함께 잰다.
**오차가 효과보다 크면 그 프로필은 룩을 충실히 전달하지 못한다** -
CLAHE 같은 적응형 연산이 강한 룩에서 실제로 일어난다(2026-09-04 실측:
`apply_canon_look` 오차 19.53 vs 효과 16.34). 발급은 하되 리포트에
`faithful: false`로 표시해 사용자가 고를 수 있게 한다.

LUT 적용 규약은 `core.lut_export.write_cube_file`과 같다 - LUT는
`[b_idx, g_idx, r_idx]`로 인덱싱되고 값은 RGB이므로 BGR 이미지에
쓰려면 출력 채널을 뒤집어야 한다(이 변환을 빠뜨리면 오차가 63까지
튄다 - 이 스크립트를 처음 쓸 때 실제로 겪은 오검증).

**한계(기존과 동일, 새로 생긴 것 아님)**: CLAHE 같은 적응형 연산은
점별 매핑으로 담을 수 없어(LUT 포맷 자체의 구조적 한계, `.cube`도 동일)
실사진 기준 평균 절대오차 ΔBGR≈21/255 수준의 근사가 된다. 캡처원
실기기 미검증 - exiftool/littlecms 구조 검증과 이 스크립트의 왕복
검증만 거쳤다.

**사용자 승인**: 2026-09-04 "캡처원용도 다 만들어"(`/goal`). 기존
배포 프로필(`*_chart.icc`/`*.dcp`/`hasselblad.json`)은 건드리지 않고
룩 DeviceLink ICC만 새로 쓴다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.build_all_capture_one_look_iccs
"""
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))

import numpy as np

from core.icc_export import write_icc_devicelink_look_from_lut
from core.lut_export import bake_lut_from_function

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "hybrid_engine", "assets", "profiles", "looks")
OUT_REPORT = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                          "capture_one_look_iccs_report.json")
LUT_SIZE = 33

# 이미 다른 이름으로 배포된 룩 - 파일명을 바꾸면 기존 사용자의 프로필이
# 사라지므로 이 배치에서 새로 쓰지 않는다(기존 파일 그대로 둔다).
ALREADY_SHIPPED = {
    ("brands.hasselblad", "apply_hncs"):
        "hybrid_engine/assets/profiles/hasselblad_hncs_look.icc",
    ("brands.fuji", "apply_provia"):
        "hybrid_engine/assets/profiles/fuji_provia_look.icc",
}


def _measure_fidelity(func, lut, size=LUT_SIZE, seed=0):
    """LUT 경유 결과와 룩 직접 호출 결과의 평균 절대오차(ΔBGR)를, 그 룩이
    원본 대비 만드는 변화량과 함께 잰다. 오차 > 효과면 프로필이 룩을
    충실히 전달하지 못한다는 뜻."""
    rng = np.random.RandomState(seed)
    img_bgr = (rng.rand(64, 64, 3) * 255).astype(np.uint8)
    direct = func(img_bgr.copy()).astype(np.float64)

    x = img_bgr.astype(np.float64) / 255.0
    b, g, r = (np.clip((x[..., i] * (size - 1)).round().astype(int), 0, size - 1)
               for i in range(3))
    out_rgb = lut[b, g, r]                      # write_cube_file 규약: [b,g,r]
    via = np.clip(out_rgb[..., ::-1] * 255.0, 0, 255)  # RGB -> BGR

    err = float(np.mean(np.abs(direct - via)))
    effect = float(np.mean(np.abs(direct - img_bgr.astype(np.float64))))
    return err, effect


def _describe(module_name, func_name):
    brand = module_name.split(".", 1)[1]
    look = func_name[len("apply_"):] if func_name.startswith("apply_") else func_name
    return brand, look, f"HNCS {brand.replace('_', ' ')} {look.replace('_', ' ')} look"


def _collect_looks():
    """구울 룩 목록을 `tests/test_brands.py`에서 모은다.

    `BRAND_LOOKS`만으로는 부족하다 - 그 자동 발견은 `brands/fuji.py`를
    통째로 제외한다(`_EXCLUDED_MODULES = {"fuji"}`, fuji는 자체
    `TestFujiPresets`가 완전성 검사를 하기 때문). 초판이 `BRAND_LOOKS`만
    썼다가 후지 필름시뮬레이션 프리셋 13개가 전부 안 구워진 걸 2026-09-04에
    발견해서, 같은 파일의 `FUJI_COLOR_PRESETS`도 합친다. 모노 프리셋
    (`FUJI_MONO_PRESETS`)은 설계상 1채널 그레이스케일을 반환해 3채널
    DeviceLink LUT로 담을 수 없으므로 제외한다.
    """
    from test_brands import BRAND_LOOKS, FUJI_COLOR_PRESETS
    return list(BRAND_LOOKS) + [("brands.fuji", fn) for fn in FUJI_COLOR_PRESETS]


def main():
    looks = _collect_looks()

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"배포 룩 {len(looks)}개 발견 (tests/test_brands.py의 BRAND_LOOKS "
          f"자동 발견 + FUJI_COLOR_PRESETS)\n")

    issued, skipped, failed = [], [], []
    for module_name, func_name in looks:
        key = (module_name, func_name)
        if key in ALREADY_SHIPPED:
            skipped.append({"module": module_name, "func": func_name,
                            "reason": "이미 다른 경로로 배포됨",
                            "existing": ALREADY_SHIPPED[key]})
            print(f"  건너뜀 {module_name}.{func_name} "
                  f"(이미 배포: {os.path.basename(ALREADY_SHIPPED[key])})")
            continue

        brand, look, description = _describe(module_name, func_name)
        out_path = os.path.join(OUT_DIR, f"{brand}_{look}.icc")
        try:
            func = getattr(importlib.import_module(module_name), func_name)
            lut = bake_lut_from_function(func, size=LUT_SIZE)
            lut = np.asarray(lut, dtype=np.float64)

            # 항등 검사: 룩이 아무것도 안 하면 LUT가 입력 격자와 같다.
            axis = np.linspace(0.0, 1.0, LUT_SIZE)
            identity = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"),
                                axis=-1)
            max_dev = float(np.max(np.abs(lut - identity)))
            if max_dev < 1e-6:
                failed.append({"module": module_name, "func": func_name,
                               "reason": f"LUT가 항등(max dev={max_dev:.2e}) - "
                                         f"굽기 실패이거나 무동작 룩"})
                print(f"  실패 {module_name}.{func_name}: LUT가 항등")
                continue

            err, effect = _measure_fidelity(func, lut)
            faithful = err < effect

            write_icc_devicelink_look_from_lut(out_path, description, lut)
            size_kb = os.path.getsize(out_path) / 1024.0
            issued.append({
                "module": module_name, "func": func_name,
                "file": os.path.relpath(out_path, BASE),
                "description": description,
                "lut_size": LUT_SIZE,
                "max_deviation_from_identity": max_dev,
                "lut_vs_direct_mean_abs_bgr": round(err, 2),
                "look_effect_mean_abs_bgr": round(effect, 2),
                "faithful": bool(faithful),
                "file_kb": round(size_kb, 1),
            })
            print(f"  발급 {brand}_{look}.icc  "
                  f"오차 {err:5.2f} / 효과 {effect:5.2f}  "
                  f"{'충실' if faithful else '※오차>효과'}")
        except Exception as e:
            failed.append({"module": module_name, "func": func_name,
                           "reason": f"{type(e).__name__}: {e}"})
            print(f"  실패 {module_name}.{func_name}: {type(e).__name__}: {e}")

    report = {
        "purpose": "Capture One DeviceLink ICC - 배포된 brands/*.py apply_* 룩 전체",
        "source_of_truth": "tests/test_brands.py BRAND_LOOKS(자동 발견) + "
                           "FUJI_COLOR_PRESETS - 테스트가 아는 룩과 캡처원 "
                           "프로필이 같은 집합이 되도록. BRAND_LOOKS는 fuji.py를 "
                           "통째로 제외하므로 FUJI_COLOR_PRESETS를 따로 합쳐야 "
                           "한다(초판이 이걸 빠뜨려 후지 프리셋 13개가 안 구워졌음). "
                           "FUJI_MONO_PRESETS는 1채널 반환이라 제외",
        "lut_size": LUT_SIZE,
        "format": "ICC DeviceLink, lut8Type('mft1') - 캡처원이 .cube를 지원 안 함",
        "limitation": "CLAHE 등 적응형 연산은 점별 LUT로 담을 수 없어 실사진 기준 "
                      "평균 절대오차 ΔBGR≈21/255 수준의 근사(.cube와 동일한 구조적 "
                      "한계). 캡처원 실기기 미검증.",
        "user_approval": "2026-09-04 '캡처원용도 다 만들어'",
        "fidelity_metric": "랜덤 BGR 이미지(64x64, seed 0)를 LUT 경유와 룩 직접 "
                           "호출로 각각 통과시킨 결과의 평균 절대오차(ΔBGR)를, "
                           "그 룩이 원본 대비 만드는 변화량(효과)과 비교. "
                           "faithful=false는 오차가 효과보다 커서 그 프로필이 룩을 "
                           "충실히 전달하지 못한다는 뜻 - CLAHE 등 적응형 연산이 "
                           "강한 룩에서 발생하며 LUT 포맷의 구조적 한계다.",
        "counts": {"issued": len(issued), "skipped": len(skipped),
                   "failed": len(failed),
                   "faithful": sum(1 for i in issued if i["faithful"]),
                   "not_faithful": sum(1 for i in issued if not i["faithful"])},
        "issued": issued, "skipped": skipped, "failed": failed,
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n발급 {len(issued)} / 건너뜀 {len(skipped)} / 실패 {len(failed)}")
    print(f"리포트: {OUT_REPORT}")
    if failed:
        print("실패가 있어 종료코드 1로 끝낸다 - 리포트의 failed 항목 확인 필요")
        sys.exit(1)


if __name__ == "__main__":
    main()
