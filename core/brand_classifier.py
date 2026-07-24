"""11개 population-fit 브랜드의 이미 계산된 시그니처(datasets/<brand>/
*_signature.json)만으로 브랜드 판별력을 검증하는 연구용 도구.
새 사진을 입력받아 예측하는 기능은 없음 - 순수하게 "이 시그니처 데이터가
브랜드를 실제로 구별할 만큼 결정력이 있는가"를 leave-one-out
교차검증으로 확인하는 게 목적. 설계 근거는
docs/superpowers/specs/2026-07-24-brand-classifier-design.md 참고."""
import json
import os

import numpy as np

DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")

BRANDS = [
    "hasselblad", "canon", "leica", "nikon", "olympus", "panasonic",
    "pentax", "phaseone", "ricoh_gr", "sigma", "sony",
]

TONE_FIELDS = ["b2", "w995", "median", "dark_pct"]
COLOR_FIELDS = ["sat_mean", "hue_mean"]
GAMUT_FIELDS = ["a_p1", "a_p99", "b_p1", "b_p99", "a_std", "b_std", "chroma_mean", "chroma_p99"]
TEXTURE_FIELDS = ["sharpening", "micro_contrast", "noise", "n_edges", "overshoot", "undershoot"]

_SIGNATURE_FILES = [
    "tone_signature.json", "color_signature.json", "gamut_signature.json", "texture_signature.json",
]


def load_signatures(brand, datasets_dir=DATASETS_DIR):
    """brand의 4개 시그니처 JSON(per_image 배열)을 filename으로 inner
    join해서 레코드 리스트를 반환. 4개 파일의 파일셋이 n_images 선언값과
    다르면(즉 조인 후 교집합이 더 작으면) 경고를 출력한다."""
    brand_dir = os.path.join(datasets_dir, brand)
    per_file = {}
    n_images_declared = None
    for fname in _SIGNATURE_FILES:
        path = os.path.join(brand_dir, fname)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if n_images_declared is None:
            n_images_declared = data.get("n_images")
        per_file[fname] = {rec["filename"]: rec for rec in data["per_image"]}

    common_filenames = set(per_file[_SIGNATURE_FILES[0]])
    for fname in _SIGNATURE_FILES[1:]:
        common_filenames &= set(per_file[fname])

    if n_images_declared is not None and len(common_filenames) != n_images_declared:
        print(
            f"경고: {brand} - 시그니처 파일 4개 조인 결과 {len(common_filenames)}장, "
            f"n_images 선언값 {n_images_declared}장과 불일치"
        )

    records = []
    for filename in sorted(common_filenames):
        merged = {"filename": filename}
        for fname in _SIGNATURE_FILES:
            merged.update(per_file[fname][filename])
        records.append(merged)
    return records
