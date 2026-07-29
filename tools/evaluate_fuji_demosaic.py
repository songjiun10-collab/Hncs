"""Fuji X-Trans 데모자이크 알고리즘(rawpy 기본 vs DHT) ΔE 비교 - 로컬에
있는 실제 raw+jpeg 페어 3쌍(fuji_pairs_manifest.csv)으로 예비 신호만
확인한다. 표본이 3장뿐이라 통계적 결론은 내지 않는다(방향 일치 여부만
보고). 설계 근거:
docs/superpowers/specs/2026-07-29-fuji-demosaic-algorithm-design.md

  python3 -m tools.evaluate_fuji_demosaic
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rawpy

from hybrid_engine.utils.evaluate import load_image_linear_for_evaluate, mean_delta_e
from hybrid_engine.utils.io import decode_raw

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(_ROOT, "fuji_pairs_manifest.csv")


def load_pairs(manifest_path=MANIFEST_PATH):
    """manifest_path(csv, 컬럼: camera/datetime/film_mode/raw_path/
    jpeg_path)를 dict 리스트로 반환 - raw_path/jpeg_path는 리포 루트
    기준 상대경로를 절대경로로 바꿔서 반환한다."""
    pairs = []
    with open(manifest_path, newline="") as f:
        for row in csv.DictReader(f):
            pairs.append({
                "camera": row["camera"],
                "datetime": row["datetime"],
                "film_mode": row["film_mode"],
                "raw_path": os.path.join(_ROOT, row["raw_path"]),
                "jpeg_path": os.path.join(_ROOT, row["jpeg_path"]),
            })
    return pairs


def compare_pair(pair):
    """(기본 데모자이크 ΔE, DHT ΔE) 반환 - 같은 카메라 JPEG 타깃 대비.
    데모자이크 알고리즘을 바꿔도 출력 해상도는 동일하므로 타깃은
    한 번만 로드한다."""
    default_linear = decode_raw(pair["raw_path"])
    dht_linear = decode_raw(pair["raw_path"], demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT)
    target = load_image_linear_for_evaluate(pair["jpeg_path"], default_linear.shape)
    de_default = mean_delta_e(default_linear, target)
    de_dht = mean_delta_e(dht_linear, target)
    return de_default, de_dht


def run_comparison():
    pairs = load_pairs()
    results = []
    for pair in pairs:
        de_default, de_dht = compare_pair(pair)
        improved = de_dht < de_default
        results.append((pair["camera"], de_default, de_dht, improved))
        print(f"  [{pair['camera']}] 기본 ΔE={de_default:.3f} DHT ΔE={de_dht:.3f} "
              f"({'DHT 개선' if improved else '기본이 더 나음'})", flush=True)
    return results


def main():
    results = run_comparison()
    n_improved = sum(1 for _, _, _, improved in results if improved)
    n_total = len(results)
    print()
    print(f"DHT가 더 나은 페어: {n_improved}/{n_total}")
    print("(표본이 작아 통계적 유의성 검정은 하지 않음 - 방향만 보고)")
    if n_improved == n_total:
        print("결론: 전 페어에서 DHT가 개선 - 방향 일치, 추가 표본으로 재검증 가치 있음")
    elif n_improved == 0:
        print("결론: 전 페어에서 기본이 더 나음 - DHT로 바꿀 근거 없음")
    else:
        print("결론: 방향이 엇갈림 - 표본 3장으로는 판단 불가")


if __name__ == "__main__":
    main()
