"""
[Protocol 1: Fidelity] RAW -> 공식 렌더러(참조 JPEG) vs RAW -> hybrid_engine.
설계 근거는 이 대화의 평가 파이프라인 설계 문서 참고 - 요약하면 ΔE 평균
하나로 뭉개지 않고 percentile/구간별/구조/채도-hue로 쪼개서 진단한다.

지금 실행 가능한 건 핫셀블라드뿐이다 - raw+jpeg 페어가 있는 유일한
브랜드(raw_calib_cache/, 13쌍). Sony/Nikon/Canon/Fuji는 이 프로젝트가
여러 번 조사했지만 raw+jpeg 페어 자체를 못 구해서(brands/canon.py,
brands/nikon.py docstring 참고) Protocol 1을 못 돌린다 - 데이터가
생기기 전까진 정직하게 "미실행"으로 남겨둔다.

  python3 -m hybrid_engine.evaluation.fidelity
  python3 -m hybrid_engine.evaluation.fidelity --profile hasselblad --out eval_report.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

from hybrid_engine.calibrate_profile import _find_pairs, _resize_max_dim, CACHE_DIR
from hybrid_engine.core import color_matrix
from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.utils.io import decode_raw, load_image_linear
from hybrid_engine.evaluation import metrics

EVAL_MAX_DIM = 1200  # 캘리브레이션(500px)보다 크게 - 평가는 진단 목적이라 디테일이 더 필요


def _load_profile(name):
    if name is None:
        return None
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "profiles", f"{name}.json")
    with open(path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    return profile


def run_fidelity(profile_name=None, max_dim=EVAL_MAX_DIM):
    pairs = _find_pairs()
    if not pairs:
        print(f"raw+jpeg 페어를 못 찾음: {CACHE_DIR}")
        return None

    engine = HybridCameraEngine(profile=_load_profile(profile_name))
    per_pair = []
    for raw_path, target_path in pairs:
        name = os.path.basename(raw_path)
        linear = _resize_max_dim(decode_raw(raw_path), max_dim)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target = load_image_linear(target_path)
        if target.shape != linear.shape:
            import cv2
            target = cv2.resize(target, (linear.shape[1], linear.shape[0]),
                                 interpolation=cv2.INTER_AREA)

        result = engine.process(linear, camera_whitebalance=camera_wb)
        report = metrics.full_report(result, target)
        report["pair"] = name
        per_pair.append(report)
        print(f"  {name:40s} ΔE mean={report['delta_e']['mean']:6.2f}  "
              f"p95={report['delta_e']['p95']:6.2f}  SSIM_L={report['ssim_L']:.3f}")

    agg = {
        "n_pairs": len(per_pair),
        "delta_e_mean_of_means": float(np.mean([r["delta_e"]["mean"] for r in per_pair])),
        "delta_e_mean_p95": float(np.mean([r["delta_e"]["p95"] for r in per_pair])),
        "delta_e_mean_max": float(np.mean([r["delta_e"]["max"] for r in per_pair])),
        "ssim_L_mean": float(np.mean([r["ssim_L"] for r in per_pair])),
        "mean_abs_dhue_deg_mean": float(np.mean(
            [r["saturation_hue"]["mean_abs_dhue_deg"] for r in per_pair])),
    }
    for zone in ("shadow", "midtone", "highlight"):
        vals = [r["delta_e_by_zone"][zone] for r in per_pair if r["delta_e_by_zone"][zone] is not None]
        agg[f"delta_e_zone_{zone}_mean"] = float(np.mean(vals)) if vals else None

    return {"per_pair": per_pair, "aggregate": agg}


def _verdict(delta_e_mean):
    if delta_e_mean < 1.0:
        return "육안 구별 불가"
    if delta_e_mean < 2.0:
        return "자세히 봐야 구별"
    if delta_e_mean < 10.0:
        return "한눈에 다름"
    return "완전히 다른 색"


def main():
    parser = argparse.ArgumentParser(description="Protocol 1: RAW->공식 렌더러 vs RAW->hybrid_engine 충실도 평가")
    parser.add_argument("--profile", default=None, help="assets/profiles/<name>.json (생략 시 기본값)")
    parser.add_argument("--out", default=None, help="JSON 리포트 저장 경로 (생략 시 stdout만)")
    args = parser.parse_args()

    print(f"핫셀블라드 raw+jpeg 페어로 Fidelity 평가 중... (profile={args.profile or 'default'})")
    result = run_fidelity(profile_name=args.profile)
    if result is None:
        sys.exit(1)

    agg = result["aggregate"]
    print(f"\n=== 종합 (n={agg['n_pairs']}) ===")
    print(f"ΔE00 평균(페어별 평균의 평균): {agg['delta_e_mean_of_means']:.2f}  "
          f"-> {_verdict(agg['delta_e_mean_of_means'])}")
    print(f"ΔE00 P95 평균: {agg['delta_e_mean_p95']:.2f}   ΔE00 max 평균: {agg['delta_e_mean_max']:.2f}")
    print(f"구간별 ΔE00: 그림자={agg['delta_e_zone_shadow_mean']}  "
          f"미드톤={agg['delta_e_zone_midtone_mean']}  하이라이트={agg['delta_e_zone_highlight_mean']}")
    print(f"SSIM(L채널) 평균: {agg['ssim_L_mean']:.4f}")
    print(f"평균 |Δhue|: {agg['mean_abs_dhue_deg_mean']:.2f}도")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\n저장: {args.out}")


if __name__ == "__main__":
    main()
