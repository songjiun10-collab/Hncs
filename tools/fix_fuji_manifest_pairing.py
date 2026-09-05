"""`tools/verify_fuji_manifest_pairing.py`가 확정한 후지 `local-work-2026-08`
매니페스트의 raw<->jpeg 오매칭을 고친다.

**무엇을 고치나**: (1) 파일번호가 서로 엇갈린 4쌍(8행)의 `filename_jpeg`를
같은 번호로 되돌린다 - RAF 내장 프리뷰 대조에서 매니페스트가 지정한 JPEG
거리 0.0911~1.1419 vs 같은 번호 JPEG 거리 0.0009~0.0019로 판정이 명확했다.
(2) 고아 행 하나(`DSCF9359.RAF,DSCF9429.JPG`)를 제거한다 - `DSCF9359.JPG`도
`DSCF9429.RAF`도 세트에 없고, `DSCF9359.RAF`에 가장 가까운 JPEG은
`DSCF9358.JPG`(거리 0.0382)라 같은 프레임조차 아니다. 두 파일 자체는
디스크에 그대로 두고 매니페스트에서만 뺀다(페어가 아닐 뿐 데이터는 유효).

**영향**: 해당 파일들 필름모드는 Classic Negative 4 / Classic Chrome 1 /
Nostalgic Neg 2로, Provia는 하나도 없다 - Provia만 거르는
`fuji_generic_jpeg_approx.icc`(n=119)는 오염되지 않았다. `apply_classic_negative`
/`apply_nostalgic_neg` 계열 보정은 영향권이며, 재보정 여부는 별도 결정이다
(이 스크립트는 매니페스트만 고치고 어떤 프로필도 건드리지 않는다).

커밋 `1a759a5`("Fuji Classic Chrome/Nostalgic Neg v2 재보정 - 페어 매칭
버그 정정판")에서 못 잡은 잔여분으로 보인다.

  python3 -m tools.fix_fuji_manifest_pairing
"""
import csv
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
MANIFEST = os.path.join(SET_DIR, "manifest.csv")

# verify_fuji_manifest_pairing.py가 확정한 오매칭 - raw -> 올바른 jpeg
SWAP_FIX = {
    "DSCF9391.RAF": "DSCF9391.JPG",
    "DSCF9422.RAF": "DSCF9422.JPG",
    "DSCF9341.RAF": "DSCF9341.JPG",
    "DSCF9342.RAF": "DSCF9342.JPG",
    "DSCF9316.RAF": "DSCF9316.JPG",
    "DSCF9328.RAF": "DSCF9328.JPG",
    "DSCF9358.RAF": "DSCF9358.JPG",
    "DSCF9428.RAF": "DSCF9428.JPG",
}
DROP_RAW = {"DSCF9359.RAF"}  # 짝이 되는 JPEG이 세트에 없는 고아 행


def main():
    with open(MANIFEST, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    fixed, dropped = [], []
    out_rows = []
    for row in rows:
        raw = row["filename_raw"]
        if raw in DROP_RAW:
            dropped.append((raw, row["filename_jpeg"]))
            continue
        if raw in SWAP_FIX and row["filename_jpeg"] != SWAP_FIX[raw]:
            fixed.append((raw, row["filename_jpeg"], SWAP_FIX[raw]))
            row["filename_jpeg"] = SWAP_FIX[raw]
        out_rows.append(row)

    for raw, was, now in fixed:
        print(f"  수정 {raw}: {was} -> {now}")
    for raw, was in dropped:
        print(f"  제거 {raw},{was} (고아 - 짝 JPEG이 세트에 없음)")

    if not fixed and not dropped:
        print("고칠 것 없음 - 이미 정정된 매니페스트다")
        return

    with open(MANIFEST, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"\n{len(fixed)}행 수정, {len(dropped)}행 제거 -> {MANIFEST}")
    print("검증: python3 -m tools.verify_fuji_manifest_pairing")


if __name__ == "__main__":
    sys.exit(main())
