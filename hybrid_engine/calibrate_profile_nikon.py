"""[research] 니콘 raw+jpeg 페어로 hybrid_engine 캘리브레이션 - 지금까지
해셀블라드 전용이던 `calibrate_profile.py`의 범용 적합 함수
(`_find_matrix_and_recalibrate`/`coordinate_descent`)를 그대로 재사용하되,
데이터 소스만 `datasets/nikon/contributed/*/manifest.csv`로 바꾼다.

`calibrate_profile.py`처럼 프로필 json에 아무것도 쓰지 않는다 - 이 스크립트는
측정만 한다. 실제로 "출시"하려면(니콘용 nikon.json을 hybrid_engine
프로필로 등록하는 것) 별도의, 사용자가 명시적으로 승인하는 결정이다
(hybrid_engine/CLAUDE.md: "Never touch" 대상은 아니지만, 루트 CLAUDE.md의
"실험 결과를 자동으로 출시하지 않는다" 원칙은 새 브랜드 프로필에도 그대로
적용).

  python3 -m hybrid_engine.calibrate_profile_nikon
"""
import csv
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.calibrate_profile import (
    _resize_max_dim,
    run_per_brand_calibration,
)
from hybrid_engine.core import color_matrix
from hybrid_engine.utils.io import decode_raw, load_image_linear

CALIB_MAX_DIM = 500
_NIKON_CONTRIBUTED_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets", "nikon", "contributed")
# 해셀블라드의 assets/luts/hasselblad_hue_learned.npy와 절대 안 겹치는
# 별도 경로 - run_hue_mode()를 그대로 부르면 그 경로에 덮어쓰므로 재사용
# 안 하고 이 파일만의 경로를 씀 (research/scratch, 커밋 대상 아님).
_NIKON_HUE_LUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "luts", "nikon_hue_learned_scratch.npy")


def _find_pairs():
    pairs = []
    for manifest_path in sorted(glob.glob(os.path.join(_NIKON_CONTRIBUTED_ROOT, "*", "manifest.csv"))):
        set_dir = os.path.dirname(manifest_path)
        with open(manifest_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                raw_path = os.path.join(set_dir, "raw", row["filename_raw"])
                jpeg_path = os.path.join(set_dir, "jpeg", row["filename_jpeg"])
                if os.path.exists(raw_path) and os.path.exists(jpeg_path):
                    pairs.append((raw_path, jpeg_path))
    return pairs


def _load_calib_set():
    dataset = []
    pairs = _find_pairs()
    for i, (raw_path, target_path) in enumerate(pairs):
        print(f"  [{i + 1}/{len(pairs)}] 로드 중: {os.path.basename(raw_path)}", flush=True)
        try:
            linear = decode_raw(raw_path)
        except Exception as e:
            print(f"    디코드 실패, 스킵: {e}")
            continue
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target_small = load_image_linear(target_path, resize_to=linear_small.shape[:2])
        dataset.append((linear_small, camera_wb, target_small))
    return dataset


if __name__ == "__main__":
    run_per_brand_calibration(
        brand_label_ko="니콘",
        dataset_glob_hint="datasets/nikon/contributed/*/manifest.csv",
        load_calib_set=_load_calib_set,
        hue_lut_scratch_path=_NIKON_HUE_LUT_PATH,
    )
