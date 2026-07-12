"""
download_fuji_pairs.py로 받은 SOOC JPEG(가공 안 한 카메라 원본 출력)를
실제 Film Mode 태그별로 묶어서 population 통계를 낸다.

raw+jpeg "같은 사진" 페어는 3장뿐이라(fuji_pairs_manifest.csv) v10~v12 방식의
픽셀 단위 캘리브레이션은 불가능하다고 판단하고 접었다. 대신 이 스크립트는
raw 없이 SOOC JPEG만으로, "실제 카메라가 만든 각 필름시뮬레이션 사진들이
평균적으로 어떤 톤/채도 통계를 갖는가"를 모드별로 비교한다 - analyze_all_samples.py
의 population 통계 방식(v9)과 같은 급으로, 페어가 아니라 그룹 간 비교다.

이어서 film_sim_presets.py 중 실제로 겹치는 프리셋(Astia, Pro Neg. Std)에 대해
"Provia로 찍힌 실제 사진에 우리 프리셋을 적용했을 때 나오는 변화 방향/크기"가
"실제 Astia/Pro Neg 사진과 실제 Provia 사진의 통계 차이"와 같은 방향인지 확인한다.
동일 장면이 아니라 서로 다른 사진들의 population 비교라서 절대값 피팅은
의미가 없고, "이 프리셋이 실제로 그 필름모드가 하는 것과 같은 방향으로
채도/톤을 움직이는가"만 검증 가능하다.
"""
import glob
import json
import os
import subprocess
from collections import defaultdict

import cv2
import numpy as np

from film_sim_presets import apply_astia, apply_pro_neg_std

CACHE_DIR = "raw_calib_cache_fuji"

# exiftool의 상세 문자열 -> 짧은 라벨
MODE_MAP = {
    "F0/Standard (Provia)": "Provia",
    "F1b/Studio Portrait Smooth Skin Tone (Astia)": "Astia",
    "F2/Fujichrome (Velvia)": "Velvia",
    "Classic Chrome": "Classic Chrome",
    "Pro Neg. Std": "Pro Neg Std",
}


def stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    p = np.percentile
    dark = (gray < 40).sum() / gray.size * 100
    return dict(
        b2=p(gray, 2), w995=p(gray, 99.5), med=np.median(gray),
        sat=s[s > 20].mean() if (s > 20).any() else 0, dark_pct=dark,
    )


def read_film_modes(paths):
    out = subprocess.run(
        ["exiftool", "-json", "-FilmMode"] + paths,
        capture_output=True, text=True, timeout=120,
    )
    data = json.loads(out.stdout) if out.stdout.strip() else []
    return {d["SourceFile"]: d.get("FilmMode") for d in data}


def main():
    jpeg_paths = sorted(glob.glob(os.path.join(CACHE_DIR, "*", "jpeg", "*.jpg")) +
                         glob.glob(os.path.join(CACHE_DIR, "*", "jpeg", "*.JPG")))
    film_modes = read_film_modes(jpeg_paths)

    groups = defaultdict(list)
    for path in jpeg_paths:
        raw_mode = film_modes.get(path)
        label = MODE_MAP.get(raw_mode)
        if not label:
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        groups[label].append(stats(img))

    print("=== 실측 필름모드별 population 통계 ===")
    agg = {}
    for label, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        b2 = np.mean([r['b2'] for r in rows])
        w995 = np.mean([r['w995'] for r in rows])
        sat = np.mean([r['sat'] for r in rows])
        agg[label] = dict(b2=b2, w995=w995, sat=sat, n=len(rows))
        print(f"{label:15s} n={len(rows):2d}  b2={b2:5.1f}  w995={w995:5.1f}  sat={sat:5.1f}")

    if "Provia" not in agg:
        print("\nProvia 기준 그룹이 없어서 프리셋 방향성 비교를 건너뜀")
        return

    print("\n=== 실측 델타 (필름모드 - Provia) vs 프리셋 델타 (프리셋(Provia사진) - Provia사진) ===")
    provia_paths = [p for p in jpeg_paths
                     if MODE_MAP.get(film_modes.get(p)) == "Provia"]

    preset_fns = {"Astia": apply_astia, "Pro Neg Std": apply_pro_neg_std}
    for label, fn in preset_fns.items():
        if label not in agg:
            print(f"{label}: 실측 표본 없어서 비교 불가")
            continue
        real_delta_sat = agg[label]['sat'] - agg['Provia']['sat']
        real_delta_b2 = agg[label]['b2'] - agg['Provia']['b2']
        real_delta_w995 = agg[label]['w995'] - agg['Provia']['w995']

        preset_sats, preset_b2s, preset_w995s = [], [], []
        for p in provia_paths:
            img = cv2.imread(p)
            if img is None:
                continue
            out = fn(img)
            st = stats(out)
            preset_sats.append(st['sat'])
            preset_b2s.append(st['b2'])
            preset_w995s.append(st['w995'])
        base_sats = [stats(cv2.imread(p))['sat'] for p in provia_paths]
        base_b2s = [stats(cv2.imread(p))['b2'] for p in provia_paths]
        base_w995s = [stats(cv2.imread(p))['w995'] for p in provia_paths]

        preset_delta_sat = np.mean(preset_sats) - np.mean(base_sats)
        preset_delta_b2 = np.mean(preset_b2s) - np.mean(base_b2s)
        preset_delta_w995 = np.mean(preset_w995s) - np.mean(base_w995s)

        def arrow(v):
            return "+" if v > 0 else ("-" if v < 0 else "0")

        print(f"\n[{label}] (실측 n={agg[label]['n']}, Provia n={len(provia_paths)})")
        print(f"  채도  실측 {real_delta_sat:+6.1f} ({arrow(real_delta_sat)})  "
              f"프리셋 {preset_delta_sat:+6.1f} ({arrow(preset_delta_sat)})  "
              f"{'일치' if arrow(real_delta_sat) == arrow(preset_delta_sat) else '불일치'}")
        print(f"  블랙p2 실측 {real_delta_b2:+6.1f} ({arrow(real_delta_b2)})  "
              f"프리셋 {preset_delta_b2:+6.1f} ({arrow(preset_delta_b2)})  "
              f"{'일치' if arrow(real_delta_b2) == arrow(preset_delta_b2) else '불일치'}")
        print(f"  화이트p99.5 실측 {real_delta_w995:+6.1f} ({arrow(real_delta_w995)})  "
              f"프리셋 {preset_delta_w995:+6.1f} ({arrow(preset_delta_w995)})  "
              f"{'일치' if arrow(real_delta_w995) == arrow(preset_delta_w995) else '불일치'}")


if __name__ == "__main__":
    main()
