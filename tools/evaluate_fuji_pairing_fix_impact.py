"""페어 오매칭 정정(`tools/fix_fuji_manifest_pairing.py`, 2026-09-04)이
후지 룩들의 측정치를 실제로 얼마나 바꿨는지 잰다 - **재보정할지는 별도
결정**이고, 이 스크립트는 그 판단 근거만 만든다.

**왜 필요한가**: 정정 커밋은 `local-work-2026-08` 매니페스트에서 raw↔jpeg가
서로 뒤바뀐 4쌍(8행)을 고쳤다. 영향 필름모드는 Classic Negative 4 /
Classic Chrome 1 / Nostalgic Neg 2로, 이 모드들의 `apply_*`가 그 세트로
검증돼 왔다. 그런데 "8행이 틀렸다"만으로는 재보정이 필요한지 알 수 없다 -
틀린 짝의 오차가 원래 오차와 비슷했다면 피팅에 준 영향이 미미하고, 훨씬
컸다면 그 프레임들이 결과를 끌고 다닌 것이다.

**방법**: 같은 모드의 모든 페어에 그 모드의 `apply_*`를 돌려 화소별 ΔE00을
낸다. 이걸 (a) 정정된 현재 매니페스트, (b) 정정 전 짝(`OLD_PAIRING`에
그대로 적어둠)으로 각각 계산한다. 8행 말고는 전부 동일하므로 페어드 차이는
그 8행에서만 생긴다 - 동점을 제외한 부호검정과, 모드 평균의 이동폭을 같이
본다. 표본이 모드당 최대 4행이라 부트스트랩 CI는 의미가 없어 내지 않고,
그 사실을 리포트에 적는다.

렌더 경로는 `tools/evaluate_fuji_preset_de00.py`와 같다
(`load_neutral_render(raw, max_dim=400)` → 룩 → 카메라 JPEG 타깃).

**배포 아님**: `brands/fuji.py`도 프로필도 건드리지 않는다. 측정만 한다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.evaluate_fuji_pairing_fix_impact
"""
import csv
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
OUT_REPORT = os.path.join(SET_DIR, "pairing_fix_impact_report.json")
MAX_DIM = 400

# 정정 전 짝 - tools/fix_fuji_manifest_pairing.py의 SWAP_FIX를 뒤집은 것.
# 여기 적힌 raw는 정정 전에 이 jpeg과 묶여 있었다.
OLD_PAIRING = {
    "DSCF9391.RAF": "DSCF9422.JPG",
    "DSCF9422.RAF": "DSCF9391.JPG",
    "DSCF9341.RAF": "DSCF9342.JPG",
    "DSCF9342.RAF": "DSCF9341.JPG",
    "DSCF9316.RAF": "DSCF9328.JPG",
    "DSCF9328.RAF": "DSCF9316.JPG",
    "DSCF9358.RAF": "DSCF9428.JPG",
    "DSCF9428.RAF": "DSCF9358.JPG",
}

MODE_TO_LOOK = {
    "Classic Negative": "apply_classic_negative",
    "Classic Chrome": "apply_classic_chrome",
    "Nostalgic Neg": "apply_nostalgic_neg",
}


def _film_mode(jpg_path):
    return subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def _to_linear(bgr_u8):
    rgb = np.clip(bgr_u8[:, :, ::-1].astype(np.float64) / 255.0, 0.0, 1.0)
    return colour.cctf_decoding(rgb, function="sRGB")


def _mean_delta_e(lin_a, lin_b):
    from skimage.color import deltaE_ciede2000, rgb2lab
    a = colour.cctf_encoding(np.clip(lin_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(lin_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def _de_for(looked_bgr, jpg_path):
    target = cv2.imread(jpg_path)
    target = cv2.resize(target, (looked_bgr.shape[1], looked_bgr.shape[0]),
                        interpolation=cv2.INTER_AREA)
    return _mean_delta_e(_to_linear(looked_bgr), _to_linear(target))


def main():
    import importlib
    fuji = importlib.import_module("brands.fuji")

    with open(os.path.join(SET_DIR, "manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    by_mode = {}
    for r in rows:
        raw_name, jpg_name = r["filename_raw"], r["filename_jpeg"]
        raw = os.path.join(SET_DIR, "raw", raw_name)
        jpg = os.path.join(SET_DIR, "jpeg", jpg_name)
        if not (os.path.exists(raw) and os.path.exists(jpg)):
            continue
        mode = _film_mode(jpg)
        if mode in MODE_TO_LOOK:
            by_mode.setdefault(mode, []).append((raw_name, jpg_name))

    results = {}
    for mode, pairs in sorted(by_mode.items()):
        look = MODE_TO_LOOK[mode]
        fn = getattr(fuji, look)
        print(f"\n[{mode}] {look}, 페어 {len(pairs)}개", flush=True)
        new_de, old_de, changed = [], [], []
        for raw_name, jpg_name in pairs:
            neutral = load_neutral_render(os.path.join(SET_DIR, "raw", raw_name),
                                          max_dim=MAX_DIM)
            looked = fn(neutral.copy())
            if looked.ndim == 2:
                looked = cv2.cvtColor(looked, cv2.COLOR_GRAY2BGR)
            d_new = _de_for(looked, os.path.join(SET_DIR, "jpeg", jpg_name))

            old_jpg = OLD_PAIRING.get(raw_name, jpg_name)
            old_path = os.path.join(SET_DIR, "jpeg", old_jpg)
            d_old = (_de_for(looked, old_path) if os.path.exists(old_path)
                     else float("nan"))
            new_de.append(d_new)
            old_de.append(d_old)
            if old_jpg != jpg_name:
                changed.append(dict(raw=raw_name, old_jpeg=old_jpg,
                                    new_jpeg=jpg_name,
                                    de00_old=round(d_old, 4),
                                    de00_new=round(d_new, 4),
                                    delta=round(d_old - d_new, 4)))
                print(f"  ※ {raw_name}: 정정전 {old_jpg} ΔE00={d_old:.4f} → "
                      f"정정후 {jpg_name} ΔE00={d_new:.4f} "
                      f"(차이 {d_old - d_new:+.4f})", flush=True)

        new_arr = np.array(new_de)
        old_arr = np.array(old_de)
        valid = ~np.isnan(old_arr)
        diff = old_arr[valid] - new_arr[valid]
        nonzero = diff[np.abs(diff) > 1e-9]
        wins = int((nonzero > 0).sum())
        losses = int((nonzero < 0).sum())
        print(f"  모드 평균 ΔE00: 정정전 {old_arr[valid].mean():.4f} → "
              f"정정후 {new_arr[valid].mean():.4f} "
              f"(이동 {old_arr[valid].mean() - new_arr[valid].mean():+.4f})")
        print(f"  바뀐 프레임 {len(nonzero)}개 중 정정 후 개선 {wins} / 악화 {losses}")
        results[mode] = dict(
            look=look, n_pairs=len(pairs),
            mean_de00_before_fix=float(old_arr[valid].mean()),
            mean_de00_after_fix=float(new_arr[valid].mean()),
            mean_shift=float(old_arr[valid].mean() - new_arr[valid].mean()),
            n_changed_frames=len(nonzero),
            changed_frames_improved=wins, changed_frames_worsened=losses,
            changed=changed)

    report = {
        "question": "페어 오매칭 정정이 후지 룩 측정치를 얼마나 바꿨나 - "
                    "재보정이 필요한지 판단할 근거",
        "fix_commit_context": "tools/fix_fuji_manifest_pairing.py (2026-09-04) - "
                              "raw<->jpeg가 뒤바뀐 4쌍(8행) 정정 + 고아 1행 제거",
        "set": "datasets/fuji/contributed/local-work-2026-08",
        "method": "같은 모드 전체 페어에 그 모드의 apply_*를 돌려 화소별 ΔE00. "
                  "정정 전 짝(OLD_PAIRING)과 정정 후 짝으로 각각 계산",
        "statistics_note": "바뀐 프레임이 모드당 최대 4개라 부트스트랩 CI는 "
                           "의미가 없어 내지 않는다. 프레임별 값과 모드 평균 "
                           "이동폭만 제시한다",
        "deployment": "배포 아님 - brands/fuji.py도 프로필도 건드리지 않는다. "
                      "재보정 여부는 사용자 결정",
        "modes": results,
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()
