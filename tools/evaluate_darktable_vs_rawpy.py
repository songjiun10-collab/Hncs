"""rawpy(decode_raw) vs darktable-cli(decode_raw_darktable) RAW 디코드
비교 - 핫셀블라드 13쌍 + Fuji 3쌍(총 16쌍) 실제 raw+jpeg 페어로 확인.
설계 근거: docs/superpowers/specs/2026-07-30-darktable-vs-rawpy-design.md

지난 두 실험(HNCS 구조 실험의 통계적 유의성 문제, Fuji 데모자이크의
멀티스레드 논디터미니즘)에서 배운 교훈으로, 실제 비교를 돌리기 전에
반복-디코드 노이즈 바닥을 ΔE 단위로 먼저 측정한다.

핫셀블라드 100MP 원본을 float64로 그대로 들면 페어당 5GB 안팎이
필요해서 16쌍을 순회하는 도중 실제로 OOM으로 프로세스가 죽었다(실측
확인) - 디코드 직후 DOWNSAMPLE_MAX_DIM으로 축소해서 피크 메모리를
낮춘다(tools/evaluate_hncs_structural.py와 같은 근거: 전역 색 분포
기반 ΔE 측정이라 공간 해상도를 낮춰도 결과를 실질적으로 왜곡하지
않는다고 본다).

darktable-cli는 시스템 패키지(apt-get install darktable)로 설치돼야
한다 - requirements.txt로 안 잡히는 이 실험 전용 의존성이다.

  python3 -m tools.evaluate_darktable_vs_rawpy
"""
import csv
import glob
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from hybrid_engine.utils.evaluate import load_image_linear_for_evaluate, mean_delta_e
from hybrid_engine.utils.io import decode_raw, decode_raw_darktable

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HASSELBLAD_CSV = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")
HASSELBLAD_CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
FUJI_MANIFEST = os.path.join(_ROOT, "fuji_pairs_manifest.csv")

# 핫셀블라드 100MP 원본을 float64로 그대로 들고 있으면(rawpy 결과 +
# darktable 결과 + 각각의 리사이즈된 JPEG 타깃까지) 페어당 5GB 안팎이
# 필요해서, 16쌍을 순회하는 도중 실제로 OOM이 나서 프로세스가 죽었다
# (실측 확인 - dmesg에 "Out of memory: Killed process ... python3"
# 기록됨). 데코드 직후 바로 축소해서 피크 메모리를 낮춘다 - 3x3
# 매트릭스나 전역 ΔE 평균처럼 공간 정보가 아니라 색 분포에 의존하는
# 측정이라 tools/evaluate_hncs_structural.py와 같은 근거로 축소가
# 결과를 실질적으로 왜곡하지 않는다고 본다.
DOWNSAMPLE_MAX_DIM = 1024


def _resize_max_dim(img, max_dim):
    """긴 변이 max_dim을 넘으면 종횡비 유지한 채 축소. 이미 작으면
    그대로 반환(no-op)."""
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return img
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img.astype(np.float32), (new_w, new_h),
                          interpolation=cv2.INTER_AREA)
    return resized.astype(np.float64)


def _hasselblad_raw_path(jpeg_name):
    matches = [m for m in glob.glob(os.path.join(HASSELBLAD_CACHE_DIR, jpeg_name + ".*"))
               if not m.endswith(".target.jpg")]
    if len(matches) != 1:
        raise FileNotFoundError(f"raw for {jpeg_name}: expected 1 match, got {matches}")
    return matches[0]


def load_hasselblad_pairs():
    """datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv의 jpeg_url
    basename 13개를 raw_calib_cache/의 실제 raw+target 경로로 매핑."""
    pairs = []
    with open(HASSELBLAD_CSV, newline="") as f:
        for row in csv.DictReader(f):
            jpeg_name = os.path.basename(row["jpeg_url"])
            pairs.append({
                "camera": "Hasselblad",
                "name": jpeg_name,
                "raw_path": _hasselblad_raw_path(jpeg_name),
                "jpeg_path": os.path.join(HASSELBLAD_CACHE_DIR, jpeg_name + ".target.jpg"),
            })
    return pairs


def load_fuji_pairs(manifest_path=FUJI_MANIFEST):
    """manifest_path(csv, 컬럼: camera/datetime/film_mode/raw_path/
    jpeg_path)를 dict 리스트로 반환 - raw_path/jpeg_path는 리포 루트
    기준 상대경로를 절대경로로 바꿔서 반환한다."""
    pairs = []
    with open(manifest_path, newline="") as f:
        for row in csv.DictReader(f):
            pairs.append({
                "camera": row["camera"],
                "name": os.path.basename(row["raw_path"]),
                "raw_path": os.path.join(_ROOT, row["raw_path"]),
                "jpeg_path": os.path.join(_ROOT, row["jpeg_path"]),
            })
    return pairs


def load_all_pairs():
    return load_hasselblad_pairs() + load_fuji_pairs()


def check_determinism(pair):
    """같은 파일을 rawpy/darktable 각각 두 번 디코드해서 재현성
    노이즈 바닥을 ΔE(CIEDE2000) 단위로 잰다(두 디코드끼리 직접 비교,
    JPEG 타깃 없이) - 실제 비교(디코더 간 ΔE 차이)와 같은 단위라야
    "노이즈보다 큰가"를 판단할 수 있다."""
    rawpy_1 = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    rawpy_2 = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    rawpy_noise_de = mean_delta_e(rawpy_1, rawpy_2)

    dt_1 = _resize_max_dim(decode_raw_darktable(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    dt_2 = _resize_max_dim(decode_raw_darktable(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    dt_noise_de = mean_delta_e(dt_1, dt_2)

    print(f"  [{pair['name']}] rawpy 반복-디코드 ΔE={rawpy_noise_de:.6f}  "
          f"darktable 반복-디코드 ΔE={dt_noise_de:.6f}", flush=True)
    return rawpy_noise_de, dt_noise_de


def compare_pair(pair):
    """(rawpy ΔE, darktable ΔE) 반환 - 같은 카메라 JPEG 타깃 대비."""
    rawpy_linear = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    dt_linear = _resize_max_dim(decode_raw_darktable(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    target_rawpy = load_image_linear_for_evaluate(pair["jpeg_path"], rawpy_linear.shape)
    target_dt = load_image_linear_for_evaluate(pair["jpeg_path"], dt_linear.shape)
    de_rawpy = mean_delta_e(rawpy_linear, target_rawpy)
    de_dt = mean_delta_e(dt_linear, target_dt)
    return de_rawpy, de_dt


def run_comparison():
    pairs = load_all_pairs()
    results = []
    for pair in pairs:
        de_rawpy, de_dt = compare_pair(pair)
        improved = de_dt < de_rawpy
        results.append((pair["camera"], pair["name"], de_rawpy, de_dt, improved))
        print(f"  [{pair['camera']}/{pair['name']}] rawpy ΔE={de_rawpy:.3f} "
              f"darktable ΔE={de_dt:.3f} "
              f"({'darktable 개선' if improved else 'rawpy가 더 나음'})", flush=True)
    return results


def main():
    print("반복-디코드 노이즈 바닥 측정 (ΔE CIEDE2000 단위, 대표 파일 각 1장):")
    hasselblad_pairs = load_hasselblad_pairs()
    fuji_pairs = load_fuji_pairs()
    noise_pairs = [check_determinism(hasselblad_pairs[0]), check_determinism(fuji_pairs[0])]
    max_noise_de = max(n for pair_noise in noise_pairs for n in pair_noise)
    print(f"측정된 최대 노이즈 바닥: ΔE {max_noise_de:.6f}")
    print()

    print("전체 16쌍 비교:")
    results = run_comparison()
    n_total = len(results)
    n_improved = sum(1 for *_, improved in results if improved)
    de_rawpy_mean = sum(r[2] for r in results) / n_total
    de_dt_mean = sum(r[3] for r in results) / n_total
    de_diff = de_rawpy_mean - de_dt_mean
    print()
    print(f"평균 rawpy ΔE (n={n_total}): {de_rawpy_mean:.3f}")
    print(f"평균 darktable ΔE (n={n_total}): {de_dt_mean:.3f}")
    print(f"평균 차이: {de_diff:.6f} (rawpy - darktable, 양수면 darktable이 더 정확)")
    print(f"darktable가 더 나은 페어: {n_improved}/{n_total}")
    print(f"측정된 노이즈 바닥(ΔE): {max_noise_de:.6f}")
    if abs(de_diff) < max_noise_de:
        print("판정: 평균 차이가 노이즈 바닥보다 작다 - 노이즈와 구분 불가")
    else:
        print("판정: 평균 차이가 노이즈 바닥보다 크다 - 노이즈로는 설명 안 되는 차이")


if __name__ == "__main__":
    main()
