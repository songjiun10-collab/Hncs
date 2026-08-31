"""
사용자 지시("노출별,iso별로,인물사진별로 나누어서 하셀도 돌려") - Canon
때(tools/breakdown_by_exposure_iso.py)와 같은 진단이지만, Hasselblad는
전용 매트릭스 피팅 파이프라인이 없으므로 새 파라미터를 만들지 않고
**실제 shipped 함수를 세대에 맞게 그대로 적용**해서(X2D II 100C ->
apply_hncs_x2dii, 나머지 -> apply_hncs - 호출부가 세대를 판별해서 쓰는
게 이 두 함수의 원래 전제) 페어별 ΔE00을 ISO/노출(EV)/인물 여부로
묶어 오차가 어디 몰려있는지 본다. 새 튜닝 아님, in-sample 진단.

  python3 -m tools.breakdown_hasselblad_by_exposure_iso_portrait
"""
import json
import multiprocessing
import os
import subprocess
import sys
import time
from collections import defaultdict

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from brands.hasselblad_x2dii import apply_hncs_x2dii
from core.validation import is_image_array_usable
from tools.calibrate import collect_local_pairs, load_neutral_render

MAX_DIM = 400
_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def _is_portrait(jpg_path):
    img = cv2.imread(jpg_path)
    if img is None:
        return False
    h, w = img.shape[:2]
    scale = 600 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    return len(faces) > 0


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    return bgr_u8_to_linear(bgr)


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def read_exif_extra(path):
    out = subprocess.run(["exiftool", "-json", "-ISO", "-ExposureCompensation", path],
                          capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    row = data[0] if data else {}
    return dict(iso=row.get("ISO"), ev=row.get("ExposureCompensation"))


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


def _decode_one(p):
    try:
        neutral = load_neutral_render(p["raw_path"], max_dim=MAX_DIM)
        target_img = cv2.imread(p["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            return p["filename"], p["generation"], None, None, None, None, "target unusable"
        target = load_target_linear(p["jpeg_path"], neutral.shape[:2])
        exif = read_exif_extra(p["raw_path"])
        portrait = _is_portrait(p["jpeg_path"])
    except Exception as e:
        return p["filename"], p["generation"], None, None, None, None, str(e)
    return p["filename"], p["generation"], neutral, target, exif, portrait, None


def main():
    rows = [p for p in collect_local_pairs() if p["scene_type"] != "chart"]
    print(f"hasselblad 실사진(챠트 제외): {len(rows)}쌍", flush=True)

    t0 = time.time()
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for i, (name, gen, neutral, target, exif, portrait, err) in enumerate(
                pool.imap_unordered(_decode_one, rows)):
            if err:
                continue
            pairs.append(dict(name=name, neutral=neutral, target=target,
                               exif=exif, portrait=portrait, generation=gen))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    n = len(pairs)
    print(f"디코드 완료: {n}개 ({time.time()-t0:.0f}s)", flush=True)

    for p in pairs:
        fn = apply_hncs_x2dii if p["generation"] == "X2D II 100C" else apply_hncs
        out = fn(p["neutral"])
        p["de00"] = mean_delta_e(bgr_u8_to_linear(out), p["target"])

    print(f"\n=== 전체 (n={n}, 세대별로 apply_hncs_x2dii/apply_hncs 실제 배포판 적용) ===")
    print(f"평균 ΔE00={np.mean([p['de00'] for p in pairs]):.3f}")

    print("\n=== 세대별 ===")
    by_gen = defaultdict(list)
    for p in pairs:
        by_gen[p["generation"]].append(p["de00"])
    for gen in sorted(by_gen, key=lambda g: -np.mean(by_gen[g])):
        vals = by_gen[gen]
        print(f"  {gen}: n={len(vals)}  평균 ΔE00={np.mean(vals):.3f}  표준편차={np.std(vals):.3f}")

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

    print("\n=== 인물/비인물 ===")
    portrait_vals = [p['de00'] for p in pairs if p['portrait']]
    non_portrait_vals = [p['de00'] for p in pairs if not p['portrait']]
    print(f"  인물(얼굴 검출됨): n={len(portrait_vals)}  평균 ΔE00={np.mean(portrait_vals):.3f}"
          if portrait_vals else "  인물: n=0")
    print(f"  비인물: n={len(non_portrait_vals)}  평균 ΔE00={np.mean(non_portrait_vals):.3f}"
          if non_portrait_vals else "  비인물: n=0")

    print("\n=== 최악 10장 (참고) ===")
    worst = sorted(pairs, key=lambda p: -p['de00'])[:10]
    for p in worst:
        print(f"  {p['name']} ({p['generation']}): ΔE00={p['de00']:.3f}  "
              f"ISO={p['exif']['iso']}  EV={p['exif']['ev']}  인물={p['portrait']}")


if __name__ == "__main__":
    main()
