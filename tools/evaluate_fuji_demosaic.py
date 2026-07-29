"""Fuji X-Trans 데모자이크 알고리즘(rawpy 기본 vs DHT) ΔE 비교 - 로컬에
있는 실제 raw+jpeg 페어 3쌍(fuji_pairs_manifest.csv)으로 확인한다.

주의(2026-07-29 최종 리뷰로 확인): LibRaw는 X-Trans 센서에서
demosaic_algorithm이 AHD/DHT/AAHD(quality>2)면 셋 다 같은 X-Trans 전용
Markesteijn 데모자이크로 합친다 - decode_raw()의 기본값도 이미 그
경로라서, 이 스크립트가 재는 "기본 vs DHT"는 X-Trans 파일에서는 사실상
같은 코드를 두 번 실행하는 것과 같다(`OMP_NUM_THREADS=1`로 스레딩을
고정하면 바이트 단위로 완전히 동일한 출력이 나온다 - 직접 확인됨).
그래서 이 결과의 진짜 의미는 "DHT가 더 낫다/아니다"가 아니라 "LibRaw가
X-Trans에 이미 전용 데모자이크를 쓰고 있어서 rawpy 안에서는 이 축으로
데모자이크 품질을 더 개선할 수 없다"는 것이다. 자세한 내용은
hybrid_engine/EVALUATION.md의 "Fuji X-Trans 데모자이크 알고리즘 비교"
절과 docs/superpowers/specs/2026-07-29-fuji-demosaic-algorithm-design.md
상단 정정 노트 참고. 스크립트/테스트는 그대로 유효하다(파라미터
전달이 정확한지 검증하는 역할은 여전함, quality<=2 알고리즘이면
실제로 다른 결과를 낸다 - PPG로 실측 확인됨) - 결론 해석만 바뀌었다.

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
    print("주의: X-Trans에서 LibRaw는 AHD/DHT/AAHD를 전부 같은 Markesteijn")
    print("데모자이크로 합친다 - 위 숫자 차이는 알고리즘 차이가 아니라")
    print("멀티스레드 디코드의 논디터미니즘이다(OMP_NUM_THREADS=1로 고정하면")
    print("바이트 단위로 동일해짐, 직접 확인됨). 자세한 내용은")
    print("hybrid_engine/EVALUATION.md 참고.")


if __name__ == "__main__":
    main()
