"""
/goal "다른 전체 브랜드 평균 e00->10미만으로" - 사용자 지시("노출별,iso별로
다 돌려")로 매트릭스+톤+채도(fit_body_matrix_plus_tone_de00.py --chroma)
파이프라인 하나를 전체 표본에서 한 번 피팅해 고정한 뒤, 그 고정
파이프라인의 페어별 ΔE00을 ISO 구간과 노출(EV, ExposureCompensation
EXIF)별로 묶어서 오차가 어디 몰려있는지 진단한다. 새로 파라미터를
찾는 게 아니라 "왜 평균이 높은가"를 보는 용도라 LOO 없이 in-sample
그대로 씀.

  python3 -m tools.breakdown_by_exposure_iso <brand> [model_filter]
"""
import csv
import multiprocessing
import os
import subprocess
import sys
import time
import json
from collections import defaultdict

import colour
import cv2
import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.curve import film_curve
from core.validation import is_image_array_usable
from tools.fit_body_matrix_plus_tone_de00 import (
    TONE_TOE_LIFT, TONE_SHOULDER_START, TONE_WHITE_POINT, TONE_CLAHE_CLIP,
    apply_tone_stage, apply_chroma_lut, fit_color_matrix, decode_raw_native,
    read_as_shot_neutral, load_target_linear, mean_delta_e,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_DIM = 400

# fit_body_matrix_plus_tone_de00.py --chroma 캐논 실행에서 나온 폴드별
# 최적값 중 가장 흔한 조합(진단용 고정 파이프라인 - 최종 채택값 아님)
FIXED_SAT_MULT = 0.75
FIXED_HUE_SHIFT = -5.0


def collect_contributed_pairs(brand, model_filter=None):
    base = os.path.join(BASE, "datasets", brand, "contributed")
    pairs = []
    seen = set()
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        for row in csv.DictReader(open(manifest, encoding="utf-8-sig")):
            if row["filename_raw"] in seen:
                continue
            if model_filter and row.get("camera") != model_filter:
                continue
            raw_path = os.path.join(base, set_name, "raw", row["filename_raw"])
            jpg_path = os.path.join(base, set_name, "jpeg", row["filename_jpeg"])
            if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
                continue
            seen.add(row["filename_raw"])
            pairs.append(dict(name=row["filename_raw"], raw_path=raw_path, jpeg_path=jpg_path,
                               manifest_iso=row.get("iso", "")))
    return pairs


def read_exif_extra(path):
    out = subprocess.run(["exiftool", "-json", "-ISO", "-ExposureCompensation", "-ShutterSpeed",
                           "-Aperture", path], capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    row = data[0] if data else {}
    return dict(iso=row.get("ISO"), ev=row.get("ExposureCompensation"),
                shutter=row.get("ShutterSpeed"), aperture=row.get("Aperture"))


def _decode_one(r):
    try:
        asn = read_as_shot_neutral(r["raw_path"])
        if asn is None:
            return r["name"], None, None, None, "no AsShotNeutral"
        native = decode_raw_native(r["raw_path"], max_dim=MAX_DIM)
        wb_rgb = native / asn
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            return r["name"], None, None, None, "target unusable"
        target = load_target_linear(r["jpeg_path"], wb_rgb.shape[:2])
        exif = read_exif_extra(r["raw_path"])
    except Exception as e:
        return r["name"], None, None, None, str(e)
    return r["name"], wb_rgb, target, exif, None


def _iso_bucket(iso):
    if iso is None:
        return "unknown"
    try:
        iso = float(iso)
    except (TypeError, ValueError):
        return "unknown"
    if iso <= 200:
        return "저ISO(<=200)"
    if iso <= 800:
        return "중ISO(201-800)"
    if iso <= 3200:
        return "고ISO(801-3200)"
    return "초고ISO(>3200)"


def _ev_bucket(ev):
    if ev is None:
        return "unknown"
    try:
        ev = float(ev)
    except (TypeError, ValueError):
        return "unknown"
    if ev <= -0.34:
        return "언더(<=-1/3EV)"
    if ev < 0.34:
        return "중립(약 0EV)"
    return "오버(>=+1/3EV)"


def main():
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    brand = positional[0]
    model_filter = positional[1] if len(positional) > 1 else None
    rows = collect_contributed_pairs(brand, model_filter)
    print(f"{brand} {model_filter or '(all)'}: manifest {len(rows)}개", flush=True)

    t0 = time.time()
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for i, (name, wb_rgb, target, exif, err) in enumerate(pool.imap_unordered(_decode_one, rows)):
            if err:
                continue
            pairs.append(dict(name=name, wb_rgb=wb_rgb, target=target, exif=exif))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    n = len(pairs)
    print(f"디코드 완료: {n}개 ({time.time()-t0:.0f}s)", flush=True)
    if n < 10:
        print("표본 부족, 종료")
        return

    matrix = fit_color_matrix([p['wb_rgb'] for p in pairs], [p['target'] for p in pairs], ridge=1.0)
    print("매트릭스 전체 표본으로 피팅 완료 (진단용 - LOO 아님, in-sample)", flush=True)

    for p in pairs:
        matrixed = np.clip(p['wb_rgb'] @ matrix, 0.0, None)
        toned = apply_tone_stage(matrixed)
        chromad = apply_chroma_lut(toned, FIXED_SAT_MULT, FIXED_HUE_SHIFT)
        p['de00'] = mean_delta_e(chromad, p['target'])

    print(f"\n=== 전체 (n={n}) ===")
    print(f"평균 ΔE00={np.mean([p['de00'] for p in pairs]):.3f}")

    print("\n=== ISO 구간별 ===")
    by_iso = defaultdict(list)
    for p in pairs:
        by_iso[_iso_bucket(p['exif']['iso'])].append(p['de00'])
    for bucket in ["저ISO(<=200)", "중ISO(201-800)", "고ISO(801-3200)", "초고ISO(>3200)", "unknown"]:
        if bucket in by_iso:
            vals = by_iso[bucket]
            print(f"  {bucket}: n={len(vals)}  평균 ΔE00={np.mean(vals):.3f}  표준편차={np.std(vals):.3f}")

    print("\n=== 노출보정(EV) 구간별 ===")
    by_ev = defaultdict(list)
    for p in pairs:
        by_ev[_ev_bucket(p['exif']['ev'])].append(p['de00'])
    for bucket in ["언더(<=-1/3EV)", "중립(약 0EV)", "오버(>=+1/3EV)", "unknown"]:
        if bucket in by_ev:
            vals = by_ev[bucket]
            print(f"  {bucket}: n={len(vals)}  평균 ΔE00={np.mean(vals):.3f}  표준편차={np.std(vals):.3f}")

    print("\n=== 최악 10장 (참고) ===")
    worst = sorted(pairs, key=lambda p: -p['de00'])[:10]
    for p in worst:
        print(f"  {p['name']}: ΔE00={p['de00']:.3f}  ISO={p['exif']['iso']}  EV={p['exif']['ev']}")


if __name__ == "__main__":
    main()
