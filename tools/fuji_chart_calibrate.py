"""
후지 필름시뮬레이션 "동일 장면 다중 모드 비교차트" 기반 검증/재보정.

tools/analyze.py의 run_fuji_film_modes()는 서로 다른 사진들을 필름모드별로
모아 population 통계를 비교하는 방식이라 장면/노출 편향이 섞인다. 이 모듈은
사용자가 리뷰 블로그/영상에서 직접 찾아 공유해준, 완전히 같은 장면·같은
노출을 여러 필름모드로 나란히 보여주는 비교차트 이미지를 쓴다 - 장면 편향이
없는 프레임 페어 비교라 population 방식보다 증거력이 강하다.

이런 비교차트는 imaging-resource.com 갤러리처럼 균일하게 스크레이핑할 수
있는 소스가 아니라(레이아웃이 이미지마다 다 다름 - grid/대각선 스트립/
세로 스트립 등), datasets/fuji/chart_comparisons/manifest.json에 각
이미지의 크롭박스(box_frac, 이미지 폭/높이 대비 비율)를 사람이 한 번씩
확인해서 손으로 기록해뒀다. 자동 경계 검출을 안 쓴 이유: 매번 다른
레이아웃에 맞는 범용 디텍터를 만드는 것보다, 사람이 직접 박스를 지정하는
쪽이 훨씬 신뢰도가 높고(이 프로젝트가 이미 imaging-resource.com CDN 손상/
mirrorlesscomparison.com 비페어링 문제로 두 번이나 데인 뒤 검증을 강화한
것과 같은 교훈), 이미지 수 자체가 수십 장 규모라 자동화 이득이 적다.

  python3 -m tools.fuji_chart_calibrate report        # 실측 delta 테이블 출력 + 저장
  python3 -m tools.fuji_chart_calibrate grid_search <preset>   # 재보정 그리드서치
"""
import json
import sys

import cv2
import numpy as np

from brands.fuji import (apply_acros, apply_astia, apply_classic_negative,
                          apply_eterna_cinema, apply_monochrome, apply_nostalgic_neg,
                          apply_pro_neg_hi, apply_pro_neg_std)
from core.stats import image_stats

MANIFEST_PATH = "datasets/fuji/chart_comparisons/manifest.json"
STATS_OUTPUT_PATH = "datasets/fuji/chart_comparison_stats.json"

# film_mode -> apply_* 함수 (Velvia/Classic Chrome/Sepia는 이 프로젝트에
# 대응하는 프리셋이 없어서 매핑 안 함 - manifest 작성 단계에서 이미 제외됨)
PRESET_FNS = {
    "Astia": apply_astia,
    "Pro Neg Std": apply_pro_neg_std,
    "Pro Neg Hi": apply_pro_neg_hi,
    "Eterna Cinema": apply_eterna_cinema,
    "Nostalgic Neg": apply_nostalgic_neg,
    "Acros": lambda img: apply_acros(img, filter_type='none'),
    "Acros Yellow Filter": lambda img: apply_acros(img, filter_type='yellow'),
    "Acros Red Filter": lambda img: apply_acros(img, filter_type='red'),
    "Acros Green Filter": lambda img: apply_acros(img, filter_type='green'),
    "Monochrome": apply_monochrome,
    "Classic Negative": apply_classic_negative,
}


def load_manifest(path=MANIFEST_PATH):
    return json.load(open(path, encoding="utf-8"))


def extract_strips(image, strips):
    """box_frac(비율 좌표) 목록대로 크롭 - grid/대각선/세로스트립 등 어떤
    레이아웃이든 박스 좌표만 맞으면 동일하게 동작(레이아웃별 분기 없음)."""
    h, w = image.shape[:2]
    out = {}
    for s in strips:
        x0, y0, x1, y1 = s["box_frac"]
        crop = image[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        out[s["film_mode"]] = crop
    return out


def compute_chart_stats(chart):
    """차트 1장 -> {film_mode: image_stats} + (Provia 베이스라인 있으면) delta.
    실패하면 (None, None) 반환."""
    img = cv2.imread(chart["image_path"])
    if img is None:
        print(f"  스킵 (로드 실패): {chart['id']}")
        return None, None
    # is_image_array_usable()은 원래 imaging-resource.com 대량 스크레이핑의
    # CDN 중간손상(균일한 빈 행)을 잡으려고 만든 것 - 사용자가 직접 찾아
    # 공유한 이 8장은 이미 육안으로 크롭 QA를 거쳤고, 레터박스 검은 띠가
    # 있는 차트(chart06)에서 "균일한 행"을 손상으로 오탐하므로 여기선
    # 적용하지 않는다.

    crops = extract_strips(img, chart["strips"])
    stats = {mode: image_stats(crop) for mode, crop in crops.items() if crop.size > 0}

    baseline = next((s["film_mode"] for s in chart["strips"] if s.get("is_baseline")), None)
    deltas = {}
    if baseline and baseline in stats:
        base = stats[baseline]
        for mode, st in stats.items():
            if mode == baseline:
                continue
            deltas[mode] = dict(d_b2=st["b2"] - base["b2"], d_w995=st["w995"] - base["w995"],
                                 d_sat=st["sat"] - base["sat"])
    return stats, deltas


def aggregate_deltas(all_deltas):
    """차트별 delta 목록 -> film_mode별 평균/표준편차/n_charts."""
    by_mode = {}
    for chart_id, deltas in all_deltas.items():
        for mode, d in deltas.items():
            by_mode.setdefault(mode, []).append(d)
    agg = {}
    for mode, rows in by_mode.items():
        agg[mode] = dict(
            n_charts=len(rows),
            d_b2=dict(mean=float(np.mean([r["d_b2"] for r in rows])), std=float(np.std([r["d_b2"] for r in rows]))),
            d_w995=dict(mean=float(np.mean([r["d_w995"] for r in rows])), std=float(np.std([r["d_w995"] for r in rows]))),
            d_sat=dict(mean=float(np.mean([r["d_sat"] for r in rows])), std=float(np.std([r["d_sat"] for r in rows]))),
        )
    return agg


def compare_to_presets(manifest):
    """차트별로 실제 apply_* 함수를 그 차트의 Provia 크롭에 걸어서
    '프리셋 delta'를 계산 - population 방식과 달리 같은 장면이라 페어링이
    유지된다."""
    preset_deltas = {}
    for chart in manifest["charts"]:
        baseline = next((s["film_mode"] for s in chart["strips"] if s.get("is_baseline")), None)
        if baseline is None:
            continue
        img = cv2.imread(chart["image_path"])
        if img is None:
            continue
        crops = extract_strips(img, chart["strips"])
        if baseline not in crops:
            continue
        base_stats = image_stats(crops[baseline])
        for mode in crops:
            if mode == baseline or mode not in PRESET_FNS:
                continue
            out = PRESET_FNS[mode](crops[baseline])
            if out.ndim == 2:  # apply_monochrome/apply_acros는 1채널 그레이스케일 반환
                out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
            st = image_stats(out)
            preset_deltas.setdefault(mode, []).append(dict(
                d_b2=st["b2"] - base_stats["b2"], d_w995=st["w995"] - base_stats["w995"],
                d_sat=st["sat"] - base_stats["sat"]))
    return {mode: dict(n=len(rows), d_b2=np.mean([r["d_b2"] for r in rows]),
                        d_w995=np.mean([r["d_w995"] for r in rows]), d_sat=np.mean([r["d_sat"] for r in rows]))
            for mode, rows in preset_deltas.items()}


def run_report():
    manifest = load_manifest()
    all_stats = {}
    all_deltas = {}
    for chart in manifest["charts"]:
        stats, deltas = compute_chart_stats(chart)
        if stats is None:
            continue
        all_stats[chart["id"]] = stats
        if deltas:
            all_deltas[chart["id"]] = deltas
        print(f"  {chart['id']} ({chart['scene_desc'][:30]}): {len(stats)}개 스트립"
              f"{', delta ' + str(len(deltas)) + '개' if deltas else ' (baseline 없어 delta 생략)'}")

    real_agg = aggregate_deltas(all_deltas)
    preset_agg = compare_to_presets(manifest)

    print(f"\n=== 실측 delta(동일장면 페어) vs 프리셋 delta ===")
    print(f"{'모드':22s} {'n차트':>6s}  {'실측d_b2':>9s} {'실측d_sat':>10s}  {'프리셋d_b2':>10s} {'프리셋d_sat':>11s}  방향일치")
    for mode in sorted(real_agg):
        r = real_agg[mode]
        p = preset_agg.get(mode)
        if p is None:
            print(f"{mode:22s} {r['n_charts']:>6d}  {r['d_b2']['mean']:>9.1f} {r['d_sat']['mean']:>10.1f}"
                  f"  {'(프리셋 없음)':>22s}")
            continue

        def arrow(v):
            return "+" if v > 0.5 else ("-" if v < -0.5 else "0")
        sat_match = arrow(r['d_sat']['mean']) == arrow(p['d_sat'])
        b2_match = arrow(r['d_b2']['mean']) == arrow(p['d_b2'])
        print(f"{mode:22s} {r['n_charts']:>6d}  {r['d_b2']['mean']:>9.1f} {r['d_sat']['mean']:>10.1f}"
              f"  {p['d_b2']:>10.1f} {p['d_sat']:>11.1f}  b2:{'OK' if b2_match else 'X '} sat:{'OK' if sat_match else 'X '}")

    output = dict(methodology=manifest["methodology"], per_chart_stats=all_stats,
                  per_chart_deltas=all_deltas, aggregated_real_deltas=real_agg,
                  preset_deltas=preset_agg)
    with open(STATS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=float)
    print(f"\n저장: {STATS_OUTPUT_PATH}")
    return output


def run_grid_search(preset_name, target_d_b2, target_d_sat, provia_crops):
    """apply_eterna_bleach_bypass/apply_classic_negative 스타일(sat_mult/
    contrast_n/black_lift/white_point 키워드)의 프리셋을 실측 delta에
    맞춰 그리드서치. provia_crops: 여러 차트의 Provia 크롭 리스트."""
    from brands.fuji import apply_classic_negative, apply_eterna_bleach_bypass
    fn = {"Classic Negative": apply_classic_negative,
          "Eterna Bleach Bypass": apply_eterna_bleach_bypass}[preset_name]

    best = None
    for sat_mult in (0.3, 0.4, 0.5, 0.65, 0.8, 1.0):
        for contrast_n in (0.8, 1.0, 1.2, 1.4, 1.7, 2.0):
            for black_lift in (0.0, 0.02, 0.05):
                err = 0.0
                for crop in provia_crops:
                    base = image_stats(crop)
                    out = fn(crop, sat_mult=sat_mult, contrast_n=contrast_n, black_lift=black_lift)
                    st = image_stats(out)
                    err += (st["b2"] - base["b2"] - target_d_b2) ** 2 + (st["sat"] - base["sat"] - target_d_sat) ** 2
                err /= max(len(provia_crops), 1)
                if best is None or err < best[0]:
                    best = (err, sat_mult, contrast_n, black_lift)
    print(f"{preset_name} 최적: RMSE={best[0] ** 0.5:.2f} sat_mult={best[1]} contrast_n={best[2]} black_lift={best[3]}")
    return best


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "report":
        run_report()
    else:
        print("usage: python3 -m tools.fuji_chart_calibrate report")
