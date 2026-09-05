"""배포 리포트의 LUT 충실도 판정이 측정 조건에 얼마나 좌우되는지 분리한다.

`hybrid_engine/assets/profiles/capture_one_look_iccs_report.json`의
`faithful` 플래그는 **64x64 난수 이미지**에 **최근접** 보간으로 잰
ΔBGR로 정해졌고, 그 기준으로 52장 중 30장이 `faithful=false`다. 그런데
캡처원/포토샵이 실제로 하는 적용은 **실사진**에 **삼선형** 보간이다.
판정이 뒤집힌다면 그 30장은 프로필의 결함이 아니라 측정 조건의 결과다.

여기서는 리포트와 **같은 단위(ΔBGR)** 로 두 요인을 각각 바꿔가며 2x2로
잰다 - 단위까지 바꾸면 어느 요인 때문인지 알 수 없기 때문이다.

  이미지: 난수(64x64, seed 0, 리포트와 동일) vs 실사진
  보간:   최근접(리포트와 동일) vs 삼선형(실제 적용 방식)

`faithful`의 정의는 리포트 그대로 - LUT 경유와 룩 직접 호출의 평균
절대오차가 그 룩이 원본 대비 만드는 변화량보다 작으면 True.

LUT은 현재 배포 방식(`core.lut_export.bake_lut_from_function`)으로 굽는다
- 이 스크립트는 굽는 방식을 비교하지 않는다(그건
`tools/evaluate_lut_bake_conditional_mean.py`).

  python3 -m tools.audit_look_lut_fidelity_metric <이미지폴더> <리포트.json>
"""
import importlib
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))

from core.lut_export import bake_lut_from_function

LUT_SIZE = 33
WORK_MAX_DIM = 1024
NOISE_SEED = 0  # 리포트의 _measure_fidelity와 동일


def _load_images(folder):
    imgs = []
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith((".jpg", ".jpeg")):
            continue
        img = cv2.imread(os.path.join(folder, f))
        h, w = img.shape[:2]
        scale = WORK_MAX_DIM / max(h, w)
        if scale < 1.0:
            img = cv2.resize(img, (int(round(w * scale)), int(round(h * scale))),
                             interpolation=cv2.INTER_AREA)
        imgs.append((f, img))
    return imgs


def _via_nearest(bgr_u8, lut, size=LUT_SIZE):
    x = bgr_u8.astype(np.float64) / 255.0
    b, g, r = (np.clip((x[..., i] * (size - 1)).round().astype(int), 0, size - 1)
               for i in range(3))
    return np.clip(lut[b, g, r][..., ::-1] * 255.0, 0, 255)


def _via_trilinear(bgr_u8, lut, size=LUT_SIZE):
    x = bgr_u8.astype(np.float64).reshape(-1, 3) / 255.0 * (size - 1)
    lo = np.clip(np.floor(x).astype(np.int64), 0, size - 2)
    frac = x - lo
    flat = lut.reshape(-1, 3)
    out = np.zeros((x.shape[0], 3), dtype=np.float64)
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = ((frac[:, 0] if db else 1.0 - frac[:, 0])
                     * (frac[:, 1] if dg else 1.0 - frac[:, 1])
                     * (frac[:, 2] if dr else 1.0 - frac[:, 2]))
                idx = ((lo[:, 0] + db) * size * size + (lo[:, 1] + dg) * size
                       + (lo[:, 2] + dr))
                out += flat[idx] * w[:, None]
    rgb = out.reshape(bgr_u8.shape)
    return np.clip(rgb[:, :, ::-1] * 255.0, 0, 255)


def _err_effect(img_bgr, direct, via):
    d = direct.astype(np.float64)
    return (float(np.mean(np.abs(d - via))),
            float(np.mean(np.abs(d - img_bgr.astype(np.float64)))))


def _collect_looks():
    from test_brands import BRAND_LOOKS, FUJI_COLOR_PRESETS
    return list(BRAND_LOOKS) + [("brands.fuji", fn) for fn in FUJI_COLOR_PRESETS]


CELLS = [("noise", "nearest"), ("noise", "trilinear"),
         ("photo", "nearest"), ("photo", "trilinear")]


def main():
    folder, out_path = sys.argv[1:3]
    photos = _load_images(folder)
    rng = np.random.RandomState(NOISE_SEED)
    noise = (rng.rand(64, 64, 3) * 255).astype(np.uint8)
    print(f"실사진 {len(photos)}장 (최대 {WORK_MAX_DIM}px) + 난수 64x64 "
          f"(seed {NOISE_SEED}, 리포트와 동일)")

    rows = []
    for module_name, func_name in _collect_looks():
        func = getattr(importlib.import_module(module_name), func_name)
        try:
            lut = bake_lut_from_function(func, size=LUT_SIZE)
        except ValueError:
            continue
        direct_noise = func(noise.copy())
        if direct_noise.ndim == 2:
            continue

        cell = {}
        for interp, fn in (("nearest", _via_nearest), ("trilinear", _via_trilinear)):
            e, eff = _err_effect(noise, direct_noise, fn(noise, lut))
            cell[f"noise/{interp}"] = {"error": e, "effect": eff, "faithful": e < eff}
        errs = {"nearest": [], "trilinear": []}
        effs = []
        for _, img in photos:
            direct = func(img.copy())
            for interp, fn in (("nearest", _via_nearest), ("trilinear", _via_trilinear)):
                e, eff = _err_effect(img, direct, fn(img, lut))
                errs[interp].append(e)
            effs.append(eff)
        for interp in ("nearest", "trilinear"):
            e, eff = float(np.mean(errs[interp])), float(np.mean(effs))
            cell[f"photo/{interp}"] = {"error": e, "effect": eff, "faithful": e < eff}

        name = f"{module_name.split('.')[1]}.{func_name}"
        rows.append({"look": name, "cells": cell})
        print(f"  {name:34s} " + "  ".join(
            f"{src[:2]}/{it[:3]} {cell[f'{src}/{it}']['error']:6.2f}"
            f"{'v' if cell[f'{src}/{it}']['faithful'] else 'x'}"
            for src, it in CELLS), flush=True)

    counts = {f"{s}/{i}": sum(r["cells"][f"{s}/{i}"]["faithful"] for r in rows)
              for s, i in CELLS}
    report = {
        "purpose": "배포 리포트의 faithful 판정이 측정 조건(이미지 소스 x 보간)에 "
                   "얼마나 좌우되는지 2x2로 분리",
        "metric": "리포트와 동일한 평균 절대오차 ΔBGR - 단위는 바꾸지 않고 "
                  "이미지 소스와 보간만 바꾼다",
        "faithful_definition": "LUT 경유 vs 룩 직접 호출 오차 < 룩이 원본 대비 만드는 효과",
        "report_condition": "noise/nearest",
        "actual_use_condition": "photo/trilinear",
        "lut_size": LUT_SIZE, "work_max_dim": WORK_MAX_DIM,
        "n_looks": len(rows), "n_photos": len(photos),
        "photos": [n for n, _ in photos],
        "faithful_counts": counts,
        "looks": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print(f"룩 {len(rows)}개, faithful 개수 (오차<효과):")
    for s, i in CELLS:
        tag = ("  <- 리포트 조건" if (s, i) == ("noise", "nearest")
               else "  <- 실제 적용 조건" if (s, i) == ("photo", "trilinear") else "")
        print(f"  {s}/{i:9s} {counts[f'{s}/{i}']:2d}/{len(rows)}{tag}")
    print(f"리포트: {out_path}")


if __name__ == "__main__":
    main()
