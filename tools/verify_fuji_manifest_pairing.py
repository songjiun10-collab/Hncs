"""후지 `local-work-2026-08` 매니페스트의 raw<->jpeg 짝이 실제로 맞는지
RAW 내장 프리뷰와 JPEG 내용을 비교해 검증한다.

**왜**: `tools/find_fuji_same_scene_film_mode_groups.py`로 같은 장면 묶음을
찾다가, 매니페스트에서 파일번호가 서로 엇갈린 행이 5쌍(9391<->9422,
9341<->9342, 9316<->9328, 9358<->9428, 9359<->9429) 눈에 띄었다. 이 세트는
과거에도 페어 매칭 버그로 재보정한 이력이 있어서(커밋 1a759a5 "Fuji Classic
Chrome/Nostalgic Neg v2 재보정 - 페어 매칭 버그 정정판") 잔여 오염인지
확인이 필요했다. 이 세트는 `apply_classic_negative` 계열 보정과
`fuji_generic_jpeg_approx.icc`(n=119) 피팅의 입력이라, 짝이 틀리면 그
결과들이 전부 오염된다.

**방법**: `exiftool -b -JpgFromRaw`(없으면 `-PreviewImage`)로 RAF 내장
프리뷰를 꺼내 32x32 표준화 그레이스케일 썸네일로 만들고, 매니페스트가
지정한 JPEG의 썸네일과 평균 절대차를 잰다. 같은 프레임이면 거의 0이어야
한다. 파일번호가 같은 다른 후보(`DSCF####.JPG`)와도 비교해서, 매니페스트가
지정한 짝보다 **번호가 같은 쪽이 더 가까우면 오매칭**으로 판정한다.

  python3 -m tools.verify_fuji_manifest_pairing
"""
import csv
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
OUT_REPORT = os.path.join(SET_DIR, "manifest_pairing_verification.json")
THUMB = 32


def _standardize(img_gray):
    t = cv2.resize(img_gray, (THUMB, THUMB), interpolation=cv2.INTER_AREA).astype(np.float64)
    return (t - t.mean()) / (t.std() + 1e-6)


def raw_preview_thumb(raw_path):
    for tag in ("-JpgFromRaw", "-PreviewImage", "-ThumbnailImage"):
        buf = subprocess.run(["exiftool", "-b", tag, raw_path],
                             capture_output=True, timeout=120).stdout
        if len(buf) > 1000:
            img = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                return _standardize(img)
    return None


def jpeg_thumb(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return None if img is None else _standardize(img)


def main():
    rows = []
    with open(os.path.join(SET_DIR, "manifest.csv"), encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f)]

    # DSCF#### 계열만 - 익명화된 해시 파일명 행은 번호 대조가 애초에 불가능하다.
    dscf = [r for r in rows if re.match(r"^DSCF\d+\.RAF$", r["filename_raw"] or "")]
    print(f"DSCF 계열 {len(dscf)}행 검증 (전체 {len(rows)}행)")

    jpeg_cache = {}

    def get_jpeg(name):
        if name not in jpeg_cache:
            p = os.path.join(SET_DIR, "jpeg", name)
            jpeg_cache[name] = jpeg_thumb(p) if os.path.exists(p) else None
        return jpeg_cache[name]

    mismatches, checked, no_preview = [], 0, []
    for r in dscf:
        raw_name, jpeg_name = r["filename_raw"], r["filename_jpeg"]
        raw_path = os.path.join(SET_DIR, "raw", raw_name)
        if not os.path.exists(raw_path):
            continue
        rt = raw_preview_thumb(raw_path)
        if rt is None:
            no_preview.append(raw_name)
            continue
        assigned = get_jpeg(jpeg_name)
        if assigned is None:
            continue
        checked += 1
        d_assigned = float(np.mean(np.abs(rt - assigned)))

        same_number = raw_name.replace(".RAF", ".JPG")
        d_same = None
        if same_number != jpeg_name:
            cand = get_jpeg(same_number)
            if cand is not None:
                d_same = float(np.mean(np.abs(rt - cand)))

        if d_same is not None and d_same < d_assigned:
            mismatches.append(dict(
                raw=raw_name, manifest_jpeg=jpeg_name,
                distance_to_manifest_jpeg=round(d_assigned, 4),
                same_number_jpeg=same_number,
                distance_to_same_number_jpeg=round(d_same, 4)))
            print(f"  오매칭 {raw_name}: 매니페스트={jpeg_name} d={d_assigned:.4f}  "
                  f"vs 같은번호={same_number} d={d_same:.4f}")

    print(f"\n프리뷰 대조 완료 {checked}행, 오매칭 {len(mismatches)}건, "
          f"프리뷰 없음 {len(no_preview)}건")
    report = {
        "purpose": "매니페스트 raw<->jpeg 짝을 RAW 내장 프리뷰로 검증",
        "set": "datasets/fuji/contributed/local-work-2026-08",
        "method": f"RAF 내장 프리뷰와 JPEG를 표준화 {THUMB}x{THUMB} 그레이스케일 "
                  f"썸네일로 만들어 평균 절대차 비교. 매니페스트가 지정한 짝보다 "
                  f"파일번호가 같은 JPEG이 더 가까우면 오매칭으로 판정",
        "n_dscf_rows": len(dscf),
        "n_checked": checked,
        "n_mismatched": len(mismatches),
        "raw_without_preview": no_preview,
        "mismatches": mismatches,
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"리포트: {OUT_REPORT}")
    if mismatches:
        sys.exit(1)


if __name__ == "__main__":
    main()
