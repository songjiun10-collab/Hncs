"""로컬 기여 raw+jpeg 페어(datasets/hasselblad/contributed/<세트>/manifest.csv)를
공식 raw+jpeg 페어 리스트에 더해주는 공용 헬퍼. evaluate_hncs_structural.py,
evaluate_chromatic_aberration.py, evaluate_hncs_blend.py 세 스크립트 모두
"공식 13쌍만 쓰던 load_pairs()"에 이 함수로 로컬 페어를 얹어 74쌍으로
확장한다(2026-08, local-mixed-2026-07 기여분 61쌍 기준). tools/calibrate.py의
collect_local_pairs()를 그대로 재사용하므로 파일 존재 확인 로직이
중복되지 않는다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.calibrate import collect_local_pairs


def load_local_pairs():
    """name/raw_path/target_path 키로 통일해 반환 - 세 evaluate 스크립트가
    공식 페어에 쓰는 dict 형태와 맞춘다(collect_local_pairs()는
    filename/raw_path/jpeg_path를 쓴다)."""
    return [
        {"name": p["filename"], "raw_path": p["raw_path"], "target_path": p["jpeg_path"]}
        for p in collect_local_pairs()
    ]


def combine_pairs(official_pairs):
    """공식 페어 리스트 뒤에 로컬 기여 페어를 이어붙여 반환."""
    return list(official_pairs) + load_local_pairs()
