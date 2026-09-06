"""같은 장면·필름모드만 다른 묶음으로, `brands/fuji.py`의 필름시뮬레이션
룩들이 **모드 간 차이를 실제만큼 만들어내는지** 잰다.

**이 데이터가 있어야만 답할 수 있는 질문**: 각 룩(`apply_classic_negative`
등)이 정말 그 모드에 특화돼 있나, 아니면 그냥 "후지 JPEG처럼" 만드는
범용 변환이고 모드끼리는 사실상 구분이 안 되나? 보통은 장면이 전부 달라서
"모드 차이"와 "장면 차이"가 섞여 이 질문을 못 던진다.
`tools/find_fuji_same_scene_film_mode_groups.py`가 찾은 같은 장면 묶음
(사용자 제보 리드, 2026-09-04)에서는 장면이 상수라 분리된다.

**재는 것 세 가지**(전부 이미지 전역 평균 Lab 사이의 ΔE00 - 묶음 안
프레임들이 픽셀 정렬돼 있지 않아 화소별 비교는 못 한다):

1. **모드 내 바닥(noise floor)**: 같은 묶음·같은 모드인 JPEG 두 장 사이
   거리. 손각대 프레이밍/노출 흔들림이 만드는 값이라, 아래 2번이 이것보다
   크지 않으면 애초에 비교가 성립하지 않는다(양성 대조 역할 -
   `hybrid_engine/CLAUDE.md`의 "null이면 양성 대조부터").
2. **실제 모드 간 거리(ground truth)**: 같은 묶음에서 모드 A JPEG과 모드 B
   JPEG 사이 거리. 카메라가 실제로 만드는 두 필름시뮬레이션의 차이다.
3. **우리 룩이 만드는 모드 간 거리**: 두 가지로 낸다.
   - `same_frame`: 같은 프레임 하나에 `apply_A`/`apply_B`를 각각 적용.
     프레임이 완전히 같아 장면 요인이 0이다.
   - `cross_frame`: **2번과 정확히 같은 프레임쌍**(모드 A 프레임의 neutral에
     `apply_A`, 모드 B 프레임의 neutral에 `apply_B`)으로 낸다.

4. **같은 룩 대조군**: `cross_frame`과 **정확히 같은 프레임쌍**에 `apply_A`를
   양쪽 다 적용한 거리. 모드 차이가 0인 조건이므로, 순수하게 룩이 증폭한
   프레임 노이즈다. `cross_frame`이 이 대조군보다 크지 않으면 그 숫자에는
   모드 분리 신호가 없다 - 초판이 이 대조군 없이 `cross_frame`을 그대로
   비율로 썼다가 3.00~4.71 같은 값이 나왔는데, 룩이 프레임 변동을 크게
   증폭시킨 것이지 모드를 그만큼 갈라놓은 게 아니었다.

**비율은 `same_frame`(장면요인 0)으로 본다** - `cross_frame`은 대조군과의
대소 비교에만 쓴다. 비율이 1에 가까우면 룩들이 실제 모드 차이만큼 벌어져
있는 것이고, 0에 가까우면 이름만 다르고 실질적으로 같은 변환, 1을 크게
넘으면 실제보다 과하게 벌려놨다는 뜻이다. 단 `same_frame` 쪽에는 장면
노이즈가 없고 실제 거리(2번)에는 있으므로, 이 비율은 **하한**으로 읽어야
한다(실제 거리가 바닥만큼 부풀려져 있다).

입력 렌더는 기존 후지 프리셋 검증과 같은 경로를 쓴다 -
`tools.calibrate.load_neutral_render(raw, max_dim=400)`
(`tools/evaluate_fuji_preset_de00.py`와 동일).

**배포 아님**: 어떤 `apply_*`나 프로필도 수정하지 않는다. 측정만 한다.

**세트 인자**: 기본은 `local-work-2026-08`. 2026-09-04에 유효 묶음이 1개
뿐이라 부트스트랩 CI를 못 냈기 때문에, 다른 세트(예:
`dpreview-gfx100rf-preprod-2026-08`)에서도 돌릴 수 있게 인자를 받는다.
같은 이름의 `same_scene_film_mode_groups.json`을 그 세트 폴더에서 읽는다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.evaluate_fuji_film_mode_separation [세트명]
"""
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRIB = os.path.join(BASE, "datasets", "fuji", "contributed")
DEFAULT_SET = "local-work-2026-08"
MAX_DIM = 400

# 세트별 경로는 main()에서 정한다. 모듈 전역으로 두면 세트 인자가 안 먹는다.
SET_DIR = os.path.join(CONTRIB, DEFAULT_SET)

# EXIF FilmMode 문자열 -> brands/fuji.py의 룩. Velvia는 대응 함수가 없어
# (FUJI_COLOR_PRESETS에 apply_velvia가 없다) 매핑에서 빠진다.
MODE_TO_LOOK = {
    "Classic Negative": "apply_classic_negative",
    "Nostalgic Neg": "apply_nostalgic_neg",
    "Classic Chrome": "apply_classic_chrome",
    "F0/Standard (Provia)": "apply_provia",
    "F1b/Studio Portrait Smooth Skin Tone (Astia)": "apply_astia",
    "Reala ACE": "apply_reala_ace",
    "Eterna": "apply_eterna_cinema",
    "Bleach Bypass": "apply_eterna_bleach_bypass",
    "Pro Neg. Hi": "apply_pro_neg_hi",
    "Pro Neg. Std": "apply_pro_neg_std",
}


def _mean_lab_of_bgr_u8(bgr_u8):
    """이미지 전역 평균 Lab. 프레이밍이 조금 달라도 안정적이고, 이
    프로젝트가 이미 쓰는 전역통계 방식(`tools/CLAUDE.md`)과 같은 성격."""
    rgb = np.clip(bgr_u8[:, :, ::-1].astype(np.float64) / 255.0, 0.0, 1.0)
    linear = colour.cctf_decoding(rgb, function="sRGB")
    xyz = colour.sRGB_to_XYZ(colour.cctf_encoding(linear, function="sRGB"))
    return colour.XYZ_to_Lab(xyz.reshape(-1, 3).mean(axis=0))


def _de00(lab_a, lab_b):
    return float(colour.delta_E(lab_a, lab_b, method="CIE 2000"))


def _load_jpeg(name):
    img = cv2.imread(os.path.join(SET_DIR, "jpeg", name))
    if img is None:
        return None
    return cv2.resize(img, (MAX_DIM, int(img.shape[0] * MAX_DIM / img.shape[1])),
                      interpolation=cv2.INTER_AREA)


def main():
    import importlib
    global SET_DIR
    set_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SET
    SET_DIR = os.path.join(CONTRIB, set_name)
    groups_json = os.path.join(SET_DIR, "same_scene_film_mode_groups.json")
    out_report = os.path.join(SET_DIR, "film_mode_separation_report.json")
    fuji = importlib.import_module("brands.fuji")

    with open(groups_json, encoding="utf-8") as f:
        groups = json.load(f)["groups"]
    print(f"세트 {set_name}: 같은 장면 묶음 {len(groups)}개 로드 ({groups_json})\n")

    results = []
    for gi, g in enumerate(groups, 1):
        frames = [fr for fr in g["frames"] if fr["film_mode"]]
        by_mode = {}
        for fr in frames:
            by_mode.setdefault(fr["film_mode"], []).append(fr)
        print(f"[묶음 {gi}] {g['camera']} {len(frames)}장, 모드 {sorted(by_mode)}")

        # JPEG 평균 Lab
        jpeg_lab = {}
        for fr in frames:
            img = _load_jpeg(fr["jpeg"])
            if img is not None:
                jpeg_lab[fr["jpeg"]] = _mean_lab_of_bgr_u8(img)

        # 1) 모드 내 바닥
        within = []
        for mode, frs in by_mode.items():
            for a, b in itertools.combinations(frs, 2):
                if a["jpeg"] in jpeg_lab and b["jpeg"] in jpeg_lab:
                    within.append(_de00(jpeg_lab[a["jpeg"]], jpeg_lab[b["jpeg"]]))
        floor = float(np.mean(within)) if within else float("nan")
        print(f"   모드 내 바닥(같은 모드 JPEG끼리) ΔE00 = {floor:.3f} (n={len(within)})")

        # neutral 렌더는 프레임당 한 번만 (RAF 디코드가 비싸다)
        neutral, neutral_lab = {}, {}
        for fr in frames:
            raw_path = os.path.join(SET_DIR, "raw", fr["raw"] or "")
            if not os.path.exists(raw_path):
                continue
            try:
                neutral[fr["jpeg"]] = load_neutral_render(raw_path, max_dim=MAX_DIM)
                neutral_lab[fr["jpeg"]] = _mean_lab_of_bgr_u8(neutral[fr["jpeg"]])
            except Exception as e:
                print(f"     디코드 실패 {fr['raw']}: {e}")

        pairs = []
        for mode_a, mode_b in itertools.combinations(sorted(by_mode), 2):
            gt = [_de00(jpeg_lab[a["jpeg"]], jpeg_lab[b["jpeg"]])
                  for a in by_mode[mode_a] for b in by_mode[mode_b]
                  if a["jpeg"] in jpeg_lab and b["jpeg"] in jpeg_lab]
            gt_mean = float(np.mean(gt)) if gt else float("nan")

            look_a, look_b = MODE_TO_LOOK.get(mode_a), MODE_TO_LOOK.get(mode_b)
            same_mean, cross_mean, ctrl_mean, base_mean = (float("nan"),) * 4
            same_vals, cross_vals, ctrl_vals, base_vals = [], [], [], []
            if look_a and look_b:
                fa, fb = getattr(fuji, look_a), getattr(fuji, look_b)
                looked_a, looked_b = {}, {}
                for name, n_img in neutral.items():
                    looked_a[name] = _mean_lab_of_bgr_u8(fa(n_img.copy()))
                    looked_b[name] = _mean_lab_of_bgr_u8(fb(n_img.copy()))
                    same_vals.append(_de00(looked_a[name], looked_b[name]))
                # 실제 거리(gt)와 정확히 같은 프레임쌍으로 - 양쪽에 같은
                # 장면 노이즈가 들어가야 비율이 공정해진다.
                for a in by_mode[mode_a]:
                    for b in by_mode[mode_b]:
                        if a["jpeg"] in looked_a and b["jpeg"] in looked_b:
                            cross_vals.append(_de00(looked_a[a["jpeg"]],
                                                    looked_b[b["jpeg"]]))
                            # 대조군: **같은 프레임쌍에 같은 룩**을 양쪽에
                            # 적용. 이건 모드 차이가 0인 조건이므로 순수하게
                            # 룩이 증폭한 프레임 노이즈다. 이 값을 안 빼면
                            # cross 거리를 모드 분리력으로 오독하게 된다
                            # (초판이 그랬다).
                            ctrl_vals.append(_de00(looked_a[a["jpeg"]],
                                                   looked_a[b["jpeg"]]))
                            # 기준선: 룩을 안 씌운 neutral 렌더끼리의 거리.
                            # 대조군이 이것보다 크면 룩이 프레임 변동을
                            # 증폭한 것이고, 비슷하면 원래 입력이 그만큼
                            # 달랐던 것뿐이다(우리 파이프라인엔 카메라의
                            # AE/AWB에 해당하는 정규화가 없다).
                            base_vals.append(_de00(neutral_lab[a["jpeg"]],
                                                   neutral_lab[b["jpeg"]]))
                same_mean = float(np.mean(same_vals)) if same_vals else float("nan")
                cross_mean = float(np.mean(cross_vals)) if cross_vals else float("nan")
                ctrl_mean = float(np.mean(ctrl_vals)) if ctrl_vals else float("nan")
                base_mean = float(np.mean(base_vals)) if base_vals else float("nan")

            def _ratio(m):
                return (m / gt_mean) if gt_mean and gt_mean == gt_mean else float("nan")

            above_floor = gt_mean > floor if gt_mean == gt_mean else False
            model_above_ctrl = (cross_mean > ctrl_mean
                                if cross_mean == cross_mean and ctrl_mean == ctrl_mean
                                else False)
            print(f"   {mode_a} vs {mode_b}")
            print(f"      실제 JPEG 모드거리 {gt_mean:.3f} (n={len(gt)}, 바닥 "
                  f"{floor:.3f} → {'유효' if above_floor else '※바닥 이하, 비교 불가'})")
            amp = (ctrl_mean / base_mean) if base_mean and base_mean == base_mean else float("nan")
            print(f"      룩 cross {cross_mean:.3f} vs 같은룩 대조군 {ctrl_mean:.3f} "
                  f"(n={len(cross_vals)}) → {'모드 신호 있음' if model_above_ctrl else '※대조군 이하 - 모드 분리 신호 없음'}")
            print(f"      프레임 변동: neutral 기준선 {base_mean:.3f} → 룩 적용 후 "
                  f"{ctrl_mean:.3f} (증폭 {amp:.2f}배, 카메라 JPEG은 {floor:.3f})")
            print(f"      same-frame(장면요인 0) {same_mean:.3f}  "
                  f"실제 대비 비율 {_ratio(same_mean):.2f}"
                  + ("" if look_a and look_b
                     else f"  [대응 함수 없음: {mode_a if not look_a else mode_b}]"))
            pairs.append(dict(mode_a=mode_a, mode_b=mode_b,
                              look_a=look_a, look_b=look_b,
                              ground_truth_de00=gt_mean, n_gt_pairs=len(gt),
                              model_cross_frame_de00=cross_mean,
                              model_same_look_control_de00=ctrl_mean,
                              neutral_baseline_cross_frame_de00=base_mean,
                              look_frame_variation_amplification=amp,
                              n_model_cross_pairs=len(cross_vals),
                              model_same_frame_de00=same_mean,
                              n_model_same_frames=len(same_vals),
                              ratio_same_frame_over_ground_truth=_ratio(same_mean),
                              ground_truth_above_within_mode_floor=bool(above_floor),
                              model_cross_above_same_look_control=bool(model_above_ctrl)))

        results.append(dict(group=gi, camera=g["camera"], n_frames=len(frames),
                            modes=sorted(by_mode),
                            within_mode_floor_de00=floor, n_within_pairs=len(within),
                            n_decoded=len(neutral), pairs=pairs))
        print()

    report = {
        "question": "brands/fuji.py의 필름시뮬레이션 룩들이 실제 모드 간 차이만큼 "
                    "서로 벌어져 있는가 - 같은 장면 묶음이라야 답할 수 있는 질문",
        "lead": "사용자 제보(2026-09-04): 후지에 같은 장면 필터만 바꿔 찍은 것 있음",
        "metric": "이미지 전역 평균 Lab 사이의 ΔE00. 묶음 안 프레임이 픽셀 정렬돼 "
                  "있지 않아 화소별 비교는 불가",
        "within_mode_floor_meaning": "같은 모드 JPEG끼리의 거리 - 프레이밍/노출 "
                                     "흔들림이 만드는 바닥. 실제 모드 간 거리가 이보다 "
                                     "크지 않으면 비교 자체가 성립하지 않는다",
        "input_render": "tools.calibrate.load_neutral_render(raw, max_dim=400) - "
                        "tools/evaluate_fuji_preset_de00.py와 동일 경로",
        "unmapped_modes": "Velvia는 brands/fuji.py에 대응 apply_* 함수가 없어 "
                          "룩 거리 계산에서 빠진다",
        "deployment": "배포 아님 - 어떤 apply_*나 프로필도 수정하지 않는다",
        "set": f"datasets/fuji/contributed/{set_name}",
        "groups": results,
    }
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out_report}")


if __name__ == "__main__":
    main()
