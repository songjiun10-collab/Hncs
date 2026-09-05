"""
Sony/Sigma/Leica ICC(Capture One)용 매트릭스는 `brands/*_raw_matrix.py`
(2026-09-02)의 매트릭스를 재사용할 수 없다 - 그건
`tools.calibrate.load_neutral_render()`(libraw가 **자체 WB+컬러매트릭스를
이미 적용한** 8비트 렌더) 위에서 피팅됐는데, ICC 카메라 프로필은
`hybrid_engine.utils.io.decode_raw_native()`가 만드는 **raw 센서
네이티브**(WB/매트릭스 적용 전) 공간을 받아야 한다 - 하셀블라드 DCP/ICC
가 애초에 그 공간으로 피팅된 이유와 같다.

이 스크립트는 그 올바른 입력공간으로 다시 피팅한다: `decode_raw_native()`
(선형, WB 우회) -> 즉시 다운샘플(`tools.calibrate._resize_to_max_dim`,
100MP 프레임 OOM 방지) -> 카메라 JPEG를 선형 sRGB로 디코드한 타깃과
3x3 최소자승(리지 정규화). **여전히 진짜 컬러체커 실측은 아니다** -
하셀블라드만 그 데이터가 있다(`hybrid_engine`의 챠트 피팅). 이건
"카메라 JPEG 근사"고, 최소한 입력 공간만 ICC가 요구하는 것과 맞다.

  python3 -m tools.fit_brand_native_matrix_for_icc <brand>
"""
import csv
import json
import multiprocessing
import os
import sys
import time

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.icc_export import write_icc_matrix_trc_profile, srgb_linear_to_xyz_d50_matrix
from core.validation import is_image_array_usable
from hybrid_engine.utils.io import decode_raw_native
from tools.calibrate import _resize_to_max_dim

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_DIM = 400

BRAND_DESCRIPTIONS = {
    "sony": "HNCS Sony Generic (JPEG-approx, not colorimetric)",
    "sigma": "HNCS Sigma Generic (JPEG-approx, not colorimetric)",
    "leica": "HNCS Leica Generic (JPEG-approx, not colorimetric)",
    "fuji": "HNCS Fuji Generic Provia (JPEG-approx, not colorimetric)",
}

# Fuji처럼 필름모드별로 다른 JPEG가 나오는 브랜드용 EXIF FilmMode 필터.
FILM_MODE_FILTER = {
    "fuji": "F0/Standard (Provia)",
}


def _exif_film_mode(jpg_path):
    import subprocess
    out = subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=10)
    return out.stdout.strip()


def collect_contributed_pairs(brand):
    film_mode_filter = FILM_MODE_FILTER.get(brand)
    base = os.path.join(BASE, "datasets", brand, "contributed")
    pairs = []
    seen = set()
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        reader = csv.DictReader(open(manifest, encoding="utf-8-sig"))
        # 2026-09에 추가된 dpreview 스튜디오씬 챠트 매니페스트는 스키마가
        # 다르다(`image_id,camera,product_id,raw_file_url,notes`) - raw+JPEG
        # 페어가 아니라 챠트 RAW 목록이라 이 스크립트의 대상이 아니다.
        # 컬럼이 없으면 KeyError로 죽던 것을 건너뛰도록 한다(2026-09-04).
        if not reader.fieldnames or not {"filename_raw", "filename_jpeg"} <= set(reader.fieldnames):
            continue
        for row in reader:
            if row["filename_raw"] in seen:
                continue
            raw_path = os.path.join(base, set_name, "raw", row["filename_raw"])
            jpg_path = os.path.join(base, set_name, "jpeg", row["filename_jpeg"])
            if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
                continue
            if film_mode_filter and _exif_film_mode(jpg_path) != film_mode_filter:
                continue
            seen.add(row["filename_raw"])
            pairs.append(dict(name=row["filename_raw"], raw_path=raw_path, jpeg_path=jpg_path))
    return pairs


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def fit_color_matrix(sources, targets, ridge=1.0):
    X = np.concatenate([s.reshape(-1, 3) for s in sources], axis=0)
    Y = np.concatenate([t.reshape(-1, 3) for t in targets], axis=0)
    k = X.shape[1]
    return np.linalg.solve(X.T @ X + ridge * np.eye(k), X.T @ Y)


def _decode_one(r):
    try:
        native = decode_raw_native(r["raw_path"])
        native = _resize_to_max_dim(native, MAX_DIM)
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            return r["name"], None, None, "target unusable"
        target = load_target_linear(r["jpeg_path"], native.shape[:2])
    except Exception as e:
        return r["name"], None, None, str(e)
    return r["name"], native, target, None


def main():
    brand = sys.argv[1]
    rows = collect_contributed_pairs(brand)
    print(f"{brand}: manifest {len(rows)}개", flush=True)
    t0 = time.time()
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for i, (name, native, target, err) in enumerate(pool.imap_unordered(_decode_one, rows)):
            if err:
                print(f"  {name} 실패: {err}", flush=True)
                continue
            pairs.append(dict(name=name, native=native, target=target))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    n = len(pairs)
    print(f"디코드 완료: {n}개 ({time.time()-t0:.0f}s)", flush=True)
    if n < 5:
        print("표본 부족, 종료")
        return

    no_correction_des = np.array([mean_delta_e(p['native'], p['target']) for p in pairs])
    print(f"매트릭스 없음(native 그대로) 기준 ΔE00 = {no_correction_des.mean():.4f}")

    # 5-fold LOO
    folds = np.array_split(np.random.RandomState(0).permutation(n), 5)
    loo_des = np.zeros(n)
    for fi, test_idx in enumerate(folds):
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        train = [pairs[i] for i in train_idx]
        matrix = fit_color_matrix([p['native'] for p in train], [p['target'] for p in train], ridge=1.0)
        for i in test_idx:
            pred = np.clip(pairs[i]['native'] @ matrix, 0.0, None)
            loo_des[i] = mean_delta_e(pred, pairs[i]['target'])
        print(f"  fold {fi+1}/5 완료", flush=True)
    print(f"매트릭스 LOO ΔE00 = {loo_des.mean():.4f} "
          f"(개선폭 {(no_correction_des.mean()-loo_des.mean())/no_correction_des.mean()*100:+.2f}%)")

    matrix = fit_color_matrix([p['native'] for p in pairs], [p['target'] for p in pairs], ridge=1.0)
    in_sample_des = np.array([
        mean_delta_e(np.clip(p['native'] @ matrix, 0.0, None), p['target']) for p in pairs
    ])
    print(f"\n전체 표본 최종 매트릭스 in-sample ΔE00 = {in_sample_des.mean():.4f}")
    print("matrix (native_linear_row @ matrix ≈ target_linear_sRGB_row) =")
    print(matrix.tolist())

    report = {
        "brand": brand,
        "n_images": n,
        "images": [p["name"] for p in pairs],
        "no_correction_delta_e_mean": float(no_correction_des.mean()),
        "matrix_cv_delta_e_mean": float(loo_des.mean()),
        "matrix_cv_delta_e_per_image": {p["name"]: float(d) for p, d in zip(pairs, loo_des)},
        "improvement_vs_no_correction_pct": float(
            (no_correction_des.mean() - loo_des.mean()) / no_correction_des.mean() * 100.0),
        "native_to_srgb_linear_matrix": matrix.tolist(),
        "matrix_in_sample_delta_e_mean": float(in_sample_des.mean()),
        "_comment": (
            "native_to_srgb_linear_matrix는 decode_raw_native()(WB/매트릭스 "
            "우회) 입력 기준 native -> 카메라 JPEG(선형 sRGB 프라이머리) "
            "근사 - 진짜 컬러체커 실측 아님(하셀블라드만 그 데이터 있음). "
            "ICC 태그용 native -> XYZ(D50) 매트릭스는 이 값에 "
            "core.icc_export.srgb_linear_to_xyz_d50_matrix()를 합성해서 만듦."
        ),
    }
    report_dir = os.path.join(BASE, "datasets", brand, "contributed")
    report_path = os.path.join(report_dir, "native_matrix_for_icc_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"저장: {report_path}")

    if brand in BRAND_DESCRIPTIONS:
        xyz_matrix = matrix @ srgb_linear_to_xyz_d50_matrix()
        icc_path = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                                 f"{brand}_generic_jpeg_approx.icc")
        write_icc_matrix_trc_profile(icc_path, xyz_matrix, description=BRAND_DESCRIPTIONS[brand])
        print(f"ICC 발급: {icc_path}")


if __name__ == "__main__":
    main()
