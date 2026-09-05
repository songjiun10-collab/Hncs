"""population fit 브랜드들이 핫셀블라드에서 **차용한** `_SHOULDER_START` /
`_CLAHE_CLIP`을 그 브랜드 자신의 raw+jpeg 페어로 재적합한다.

**왜 필요한가**: `brands/*.py` 10개(canon, leica, nikon, olympus, panasonic,
pentax, phaseone, ricoh_gr, sigma, sony)가 코드에 스스로
`# 미검증 - 핫셀블라드 기본값 차용`이라고 적어둔 채
`_SHOULDER_START = 0.78`, `_CLAHE_CLIP = 1.25`를 쓰고 있다.
`_TOE_LIFT`/`_WHITE_POINT`는 브랜드별 JPEG 통계로 실측했지만 이 둘은
raw+jpeg 페어가 없어서 못 쟀던 것이다. 그래서 재적합은 **2축 그리드**로
끝난다 - 실측된 두 축은 그대로 고정한다.

**방법**: 브랜드 모듈에서 현행 상수 4개를 그대로 읽어 기준선으로 삼고,
`shoulder_start` x `clahe_clip` 격자를 LOO(표본이 작아 k-fold 대신)로 돌린다.
폴드마다 학습쪽에서 콤보를 새로 고르므로 데이터 누수가 없다.

**성공 기준(결과 보기 전에 확정)**: LOO 홀드아웃에서 이미지별 ΔE00을 현행
차용값과 페어드로 비교해 **부트스트랩 95% CI(20000회, 고정 시드)가 0을
배제하고 신규가 우세할 때만** 교체를 권고한다. CI가 0을 포함하면 개선폭이
좋아 보여도 "판정 보류, 현행 유지"다. 폴드 선택이 갈리면 그 사실도 함께
적는다 - 만장일치가 아니면 신호가 약하다는 뜻이다.

**주의**: 이 스크립트는 `brands/*.py`를 수정하지 않는다. 상수 교체는 배포
결정이다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.refit_borrowed_population_fit_params \\
      --brand brands.leica \\
      --set datasets/leica/contributed/dpreview-sl3p-2026-08
"""
import argparse
import csv
import importlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from core.curve import film_curve
from hybrid_engine.utils.evaluate import bgr_u8_to_linear_rgb, mean_delta_e
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 400

# 1차 실행(shoulder <=0.90, clahe >=1.0)에서 라이카가 두 축 모두 경계
# (0.90 / 1.0)에 15/15 만장일치로 붙어서 양쪽을 넓혔다. clahe_clip은 0
# 이하로 내리면 OpenCV가 클리핑을 끄고 오히려 로컬대비가 최대가 되므로
# 양수 하한(0.4)까지만 내린다 - "CLAHE를 끄는" 방향이 아니라는 뜻이다.
# 라이카 LOO가 15/15 만장일치로 0.99(당시 상한)에 붙어서 film_curve의
# 실제 clamp(0.999)까지 더 밀어 재확인한다 - 이 세션에서 이미 두 번(라이카
# 1차, Classic Negative v2) 좁은 격자의 경계 결과가 넓히면 뒤집혔다.
SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82, 0.86, 0.90,
                   0.94, 0.97, 0.99, 0.995, 0.999)
CLAHE_CLIPS = (0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0)
COMBOS = [(s, c) for s in SHOULDER_STARTS for c in CLAHE_CLIPS]


def apply_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip):
    """`core.engine.make_population_fit_look`이 만드는 것과 같은 파이프라인."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n))


def summarize(base, new, n_bootstrap=20000, seed=0):
    d = np.asarray(base, float) - np.asarray(new, float)
    n = len(d)
    rng = np.random.default_rng(seed)
    boot = np.array([d[rng.integers(0, n, n)].mean() for _ in range(n_bootstrap)])
    lo, hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    wins, losses = int((d > 0).sum()), int((d < 0).sum())
    p = _sign_test_p(wins, losses)
    incon = lo <= 0.0 <= hi
    print(f"\n평균 현행(차용) ΔE00={np.mean(base):.4f}  "
          f"평균 재적합 ΔE00={np.mean(new):.4f}  "
          f"개선폭={100.0 * d.mean() / np.mean(base):+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}  "
          f"부트스트랩 95% CI=[{lo:+.4f}, {hi:+.4f}]")
    verdict = ("판정 보류 (CI가 0 포함)" if incon
               else ("재적합 우세" if d.mean() > 0 else "현행 차용값 우세"))
    print(f"판정: {verdict}")
    return dict(mean_base=float(np.mean(base)), mean_new=float(np.mean(new)),
                n=n, wins=wins, losses=losses, p_value=p, ci_lo=lo, ci_hi=hi,
                inconclusive=bool(incon), verdict=verdict)


def load_pairs(set_dirs, max_pairs=None):
    grids, confirms, tg, tc, names = [], [], [], [], []
    for rel in set_dirs:
        d = os.path.join(BASE, rel)
        man = os.path.join(d, "manifest.csv")
        if not os.path.exists(man):
            print(f"  매니페스트 없음, 건너뜀: {rel}")
            continue
        with open(man, encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                jpg = os.path.join(d, "jpeg", r["filename_jpeg"])
                raw = os.path.join(d, "raw", r["filename_raw"])
                if not (os.path.exists(jpg) and os.path.exists(raw)):
                    continue
                try:
                    g = load_neutral_render(raw, max_dim=GRID_MAX_DIM)
                    c = load_neutral_render(raw, max_dim=CONFIRM_MAX_DIM)
                except Exception as e:
                    print(f"  디코드 실패({type(e).__name__}), 건너뜀: "
                          f"{r['filename_raw']}")
                    continue
                j = cv2.imread(jpg)
                if j is None:
                    continue
                grids.append(g)
                tg.append(cv2.resize(j, (g.shape[1], g.shape[0]),
                                     interpolation=cv2.INTER_AREA))
                confirms.append(c)
                tc.append(cv2.resize(j, (c.shape[1], c.shape[0]),
                                       interpolation=cv2.INTER_AREA))
                names.append(f"{rel}/{r['filename_raw']}")
                if max_pairs and len(names) >= max_pairs:
                    return grids, tg, confirms, tc, names
    return grids, tg, confirms, tc, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True, help="예: brands.leica")
    ap.add_argument("--set", action="append", required=True, dest="sets",
                    help="datasets/... 상대경로, 여러 번 지정 가능")
    ap.add_argument("--max-pairs", type=int, default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--control-shoulder", type=float, default=None,
                    help="양성 대조용 - 기준선의 shoulder_start를 일부러 "
                         "틀린 값으로 바꿔 도구가 그걸 잡아내는지 본다")
    ap.add_argument("--control-clahe", type=float, default=None,
                    help="양성 대조용 - 기준선의 clahe_clip을 일부러 틀린 값으로")
    args = ap.parse_args()

    mod = importlib.import_module(args.brand)
    cur = dict(toe_lift=mod._TOE_LIFT, shoulder_start=mod._SHOULDER_START,
               white_point=mod._WHITE_POINT, clahe_clip=mod._CLAHE_CLIP)
    is_control = args.control_shoulder is not None or args.control_clahe is not None
    if is_control:
        if args.control_shoulder is not None:
            cur["shoulder_start"] = args.control_shoulder
        if args.control_clahe is not None:
            cur["clahe_clip"] = args.control_clahe
        print("*** 양성 대조 실행 - 기준선을 일부러 틀린 값으로 바꿨다. "
              "여기서 '재적합 우세'가 안 나오면 도구가 차이를 못 잡는 것이다 ***")
    print(f"[{args.brand}] 현행 상수 {cur}")
    print(f"  실측 고정: toe_lift={cur['toe_lift']:.6f}, "
          f"white_point={cur['white_point']:.6f}")
    print(f"  재적합 대상(차용): shoulder_start={cur['shoulder_start']}, "
          f"clahe_clip={cur['clahe_clip']}\n")

    grids, tg, confirms, tc, names = load_pairs(args.sets, args.max_pairs)
    n = len(names)
    print(f"\n사용 가능 페어 {n}개, 콤보 {len(COMBOS)}개")
    if n < 8:
        print("표본 부족(8쌍 미만) - 재적합하지 않는다")
        return

    tg_linear = [bgr_u8_to_linear_rgb(t) for t in tg]
    tc_linear = [bgr_u8_to_linear_rgb(t) for t in tc]

    def grid_de(idxs, combo):
        ss, cc = combo
        return float(np.mean([mean_delta_e(
            bgr_u8_to_linear_rgb(
                apply_look(grids[i], cur["toe_lift"], ss, cur["white_point"], cc)),
            tg_linear[i]) for i in idxs]))

    de_cur, de_new, picks = [], [], []
    for i in range(n):  # LOO - 표본이 작아 k-fold 대신
        train = [k for k in range(n) if k != i]
        best = min(COMBOS, key=lambda c: grid_de(train, c))
        picks.append(list(best))
        de_cur.append(mean_delta_e(
            bgr_u8_to_linear_rgb(apply_look(confirms[i], **cur)), tc_linear[i]))
        de_new.append(mean_delta_e(
            bgr_u8_to_linear_rgb(apply_look(confirms[i], cur["toe_lift"], best[0],
                                            cur["white_point"], best[1])),
            tc_linear[i]))
        print(f"  [{i + 1}/{n}] 선택 shoulder={best[0]} clahe={best[1]}  "
              f"현행 {de_cur[-1]:.4f} -> 재적합 {de_new[-1]:.4f}", flush=True)

    print(f"\n=== LOO 홀드아웃 (데이터 누수 없음) ===")
    stats = summarize(de_cur, de_new)

    full = min(COMBOS, key=lambda c: grid_de(list(range(n)), c))
    uniq = {tuple(p) for p in picks}
    unanimous = len(uniq) == 1
    print(f"\n전체 표본 최종: shoulder_start={full[0]}, clahe_clip={full[1]}  "
          f"(현행 {cur['shoulder_start']}, {cur['clahe_clip']})")
    print(f"폴드 만장일치: {'예' if unanimous else f'아니오 ({len(uniq)}종)'}")
    edges = []
    if full[0] in (min(SHOULDER_STARTS), max(SHOULDER_STARTS)):
        edges.append("shoulder_start")
    if full[1] in (min(CLAHE_CLIPS), max(CLAHE_CLIPS)):
        edges.append("clahe_clip")
    print(f"격자 경계에 붙은 축: {edges or '없음'}")

    passed = (not stats["inconclusive"]) and stats["mean_new"] < stats["mean_base"]
    print(f"\n성공 기준(CI가 0 배제 + 재적합 우세) 충족: {'예' if passed else '아니오'}")
    print(f"권고: {'상수 교체 제안 (배포는 사용자 결정)' if passed else '현행 유지'}"
          + (f" / 다만 {edges} 축이 격자 경계라 범위 재확인 필요" if passed and edges else ""))

    suffix = "_control" if is_control else ""
    out = args.json_out or os.path.join(
        BASE, "datasets",
        f"refit_borrowed_{args.brand.split('.')[-1]}{suffix}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "purpose": "핫셀블라드에서 차용한 shoulder_start/clahe_clip을 그 "
                       "브랜드 자신의 raw+jpeg 페어로 재적합",
            "criterion": "LOO 홀드아웃 페어드 부트스트랩 95% CI 20000회 고정 "
                         "시드가 0을 배제하고 재적합이 우세할 때만 교체 권고",
            "brand": args.brand, "sets": args.sets,
            "current_constants": cur, "n_pairs": n, "images": names,
            "grid": {"shoulder_start": list(SHOULDER_STARTS),
                     "clahe_clip": list(CLAHE_CLIPS)},
            "loo_picks": picks, "loo_unanimous": unanimous,
            "full_sample_combo": list(full),
            "params_on_grid_edge": edges,
            "delta_e_current": de_cur, "delta_e_refit": de_new,
            "stats": stats, "criterion_passed": bool(passed),
            "is_positive_control": bool(is_control),
            "modifies_shipped_code": False,
        }, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out}")


if __name__ == "__main__":
    main()
