"""브랜드 시그니처 판별기 CLI - 10개 브랜드(ricoh_gr은 hue_median/hue_mean
통계 불일치로 제외, EXCLUDED_BRANDS 참고)의 이미 계산된 population
시그니처(datasets/*/*_signature.json)만으로 leave-one-out 교차검증 기반
nearest-centroid 분류를 돌려서 confusion matrix와 지표를 출력한다
(서브커맨드 없이 실행, 기본 동작).

`predict` 서브커맨드는 별도 목적 - "재미용"으로 임의의 새 사진 한 장을
10개 브랜드 centroid와 비교해서 거리 순위를 매긴다. texture 없이
Set A(tone_color_gamut)만 지원(core/photo_signature.py 모듈 docstring
참고 - 브랜드별 texture 계산 공식이 유실돼 새 사진에 재현 불가). 이
판별기의 실측 정확도(19.6%, 다수결 baseline 14.6%)가 낮기 때문에
가짜 확률을 표시하지 않고 거리 순위만 보여준다(설계 근거:
docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md)."""
import argparse
import base64
import csv
import os
import sys

import cv2
import numpy as np

from core.brand_classifier import (
    BRANDS, load_signatures, extract_features, nearest_centroid_loo,
    confusion_matrix, classification_report, rank_brands_by_distance,
)
from core.photo_signature import compute_signature

ACCURACY_CAVEAT = (
    "참고: 이 판별기의 실측 정확도는 19.6%(다수결 baseline 14.6%) - "
    "순위는 참고용이지 확정적 판정이 아님"
)

# datasets/ricoh_gr/color_signature.json stores hue_median instead of
# hue_mean (the only one of the 11 brands that does), so its hue feature
# isn't computed on the same basis as the other 10 brands' - including it
# would let the classifier partly key off a data-collection artifact
# instead of a genuine color-rendering difference.
EXCLUDED_BRANDS = {"ricoh_gr"}

CLASSIFIED_BRANDS = [b for b in BRANDS if b not in EXCLUDED_BRANDS]


def load_all_features(feature_set):
    """CLASSIFIED_BRANDS(ricoh_gr 제외 10개 브랜드) 전체를 로드해서
    (X, y) 반환 - report 모드와 predict 모드가 함께 재사용한다."""
    all_X = []
    all_y = []
    for brand in CLASSIFIED_BRANDS:
        records = load_signatures(brand)
        X, _ = extract_features(records, feature_set=feature_set)
        all_X.append(X)
        all_y.extend([brand] * len(records))
    X = np.concatenate(all_X, axis=0)
    y = np.array(all_y)
    return X, y


def run(feature_set):
    X, y = load_all_features(feature_set)
    predictions = nearest_centroid_loo(X, y)
    matrix = confusion_matrix(y, predictions, brands=CLASSIFIED_BRANDS)
    report = classification_report(y, predictions, brands=CLASSIFIED_BRANDS)
    return matrix, report


def print_report(matrix, report, feature_set):
    print(f"=== feature_set={feature_set} ===")
    header = "true\\pred".ljust(12) + "".join(b[:8].rjust(9) for b in CLASSIFIED_BRANDS)
    print(header)
    for i, brand in enumerate(CLASSIFIED_BRANDS):
        row = brand.ljust(12) + "".join(str(matrix[i, j]).rjust(9) for j in range(len(CLASSIFIED_BRANDS)))
        print(row)
    print()
    print(f"{'brand':<12}{'n':>6}{'precision':>12}{'recall':>10}{'f1':>8}")
    for brand in CLASSIFIED_BRANDS:
        stats = report["per_brand"][brand]
        print(f"{brand:<12}{stats['n']:>6}{stats['precision']:>12.3f}{stats['recall']:>10.3f}{stats['f1']:>8.3f}")
    print()
    print(f"overall accuracy: {report['accuracy']:.3f}")
    print(f"macro accuracy (balanced): {report['macro_accuracy']:.3f}")
    print(f"majority-class baseline: {report['majority_baseline']:.3f}")
    print(f"uniform baseline (1/{len(CLASSIFIED_BRANDS)}): {report['uniform_baseline']:.3f}")


def write_csv(matrix, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["true\\pred"] + CLASSIFIED_BRANDS)
        for i, brand in enumerate(CLASSIFIED_BRANDS):
            writer.writerow([brand] + list(matrix[i]))


def run_predict(photo_path):
    img = cv2.imread(photo_path)
    if img is None:
        sys.exit(f"이미지를 읽을 수 없음: {photo_path}")

    signature = compute_signature(img)
    query_vector, _ = extract_features([signature], feature_set="tone_color_gamut")
    query_vector = query_vector[0]

    train_X, train_y = load_all_features("tone_color_gamut")
    ranking = rank_brands_by_distance(query_vector, train_X, train_y)
    return ranking


def print_predict_report(ranking):
    print(ACCURACY_CAVEAT)
    print(f"\n1위: {ranking[0][0]} (거리 {ranking[0][1]:.3f})\n")
    print(f"{'순위':<4}{'브랜드':<12}{'거리':>10}")
    for rank, (brand, dist) in enumerate(ranking, start=1):
        print(f"{rank:<4}{brand:<12}{dist:>10.3f}")


def write_predict_html(photo_path, ranking, html_path):
    """사진(base64 내장) + 순위표 + 정확도 경고 배너가 담긴 자기완결적
    정적 HTML 파일을 만든다. 외부 CDN/폰트 의존 없음(시스템 폰트만 사용).
    미니멀/무채색 톤(다크 배경, 회색조 팔레트, 색 액센트 없음) - 코너
    브래킷 뷰파인더 프레임과 모노스페이스 라벨은 사용자가 공유한 다른
    데모 페이지의 에디토리얼 톤에서 아이디어만 가져온 것으로, 그 페이지의
    인터랙티브 JS 엔진은 가져오지 않는다(이 리포트는 정적 결과물)."""
    with open(photo_path, "rb") as f:
        photo_b64 = base64.b64encode(f.read()).decode("ascii")
    ext = os.path.splitext(photo_path)[1].lstrip(".").lower() or "jpeg"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext

    top_brand, top_dist = ranking[0]
    rows = "\n".join(
        f'<div class="bitem{" active" if i == 1 else ""}">'
        f'<span class="idx">{i:02d}</span>'
        f'<span class="bn">{brand}</span>'
        f'<span class="bd">{dist:.3f}</span>'
        f'</div>'
        for i, (brand, dist) in enumerate(ranking, start=1)
    )

    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>브랜드 시그니처 예측 (재미용)</title>
<style>
:root{{
  --bg:#0a0a0a; --bg2:#101010; --bg3:#181817;
  --fg:#f2f2f0; --fg2:#c9c9c4; --mut:#8b8b86; --dim:#4c4c48;
  --line:#232321; --line2:#373733;
  --mono:ui-monospace,SFMono-Regular,'IBM Plex Mono',monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Malgun Gothic',sans-serif;
  --maxw:920px;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:var(--sans);background:var(--bg);color:var(--fg);line-height:1.6;padding:0 0 60px}}
.wrap{{max-width:var(--maxw);margin:0 auto;padding:0 28px}}
.top{{border-bottom:1px solid var(--line);padding:18px 0;margin-bottom:36px}}
.top-in{{max-width:var(--maxw);margin:0 auto;padding:0 28px;display:flex;align-items:center;gap:10px}}
.led{{width:7px;height:7px;border-radius:50%;background:var(--fg);flex:none}}
.wm{{font-family:var(--mono);font-size:.72rem;letter-spacing:.14em;color:var(--mut);text-transform:uppercase}}
h1{{font-size:clamp(1.5rem,4vw,2.1rem);font-weight:800;letter-spacing:-.01em;margin-bottom:8px}}
.kicker{{font-family:var(--mono);font-size:.64rem;letter-spacing:.18em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}}
.warn{{background:var(--bg2);border:1px solid var(--fg2);color:var(--fg2);
  font-family:var(--mono);font-size:.74rem;letter-spacing:.02em;padding:12px 16px;
  margin-bottom:32px;line-height:1.7}}
.grid{{display:grid;grid-template-columns:280px 1fr;gap:32px}}
.frame{{position:relative;border:1px dashed var(--line2);padding:10px}}
.corner{{position:absolute;width:13px;height:13px;border:1px solid var(--fg);opacity:.8}}
.c-tl{{top:6px;left:6px;border-right:none;border-bottom:none}}
.c-tr{{top:6px;right:6px;border-left:none;border-bottom:none}}
.c-bl{{bottom:6px;left:6px;border-right:none;border-top:none}}
.c-br{{bottom:6px;right:6px;border-left:none;border-top:none}}
.frame img{{display:block;width:100%;height:auto}}
.frame-cap{{font-family:var(--mono);font-size:.6rem;letter-spacing:.12em;color:var(--dim);
  text-transform:uppercase;margin-top:10px}}
.result{{margin-bottom:18px}}
.result .lbl{{font-family:var(--mono);font-size:.62rem;letter-spacing:.18em;color:var(--mut);
  text-transform:uppercase;margin-bottom:6px}}
.result .val{{font-size:1.7rem;font-weight:800}}
.result .dist{{font-family:var(--mono);font-size:.78rem;color:var(--mut)}}
.blist{{border-top:1px solid var(--fg)}}
.bitem{{display:grid;grid-template-columns:26px 1fr auto;align-items:center;gap:10px;
  padding:9px 4px;border-bottom:1px solid var(--line);font-size:.86rem}}
.bitem .idx{{font-family:var(--mono);font-size:.62rem;color:var(--dim)}}
.bitem .bd{{font-family:var(--mono);font-size:.72rem;color:var(--mut)}}
.bitem.active{{background:var(--fg);color:var(--bg)}}
.bitem.active .idx,.bitem.active .bd{{color:var(--bg)}}
footer{{margin-top:40px;font-family:var(--mono);font-size:.62rem;color:var(--dim);
  letter-spacing:.04em;line-height:1.8}}
@media(max-width:640px){{.grid{{grid-template-columns:1fr}}}}
</style></head>
<body>
<div class="top"><div class="top-in"><span class="led"></span><span class="wm">HNCS &middot; PREDICT (재미용)</span></div></div>
<div class="wrap">
  <div class="kicker">Brand Signature Ranking &middot; Not a Verified Match</div>
  <h1>{top_brand}에 가장 가까움</h1>
  <div class="warn">{ACCURACY_CAVEAT}. 가짜 확률이 아니라 거리 순위만 표시함.</div>
  <div class="grid">
    <div>
      <div class="frame">
        <i class="corner c-tl"></i><i class="corner c-tr"></i><i class="corner c-bl"></i><i class="corner c-br"></i>
        <img src="data:image/{mime};base64,{photo_b64}" alt="입력 사진">
      </div>
      <div class="frame-cap">Query Photo</div>
    </div>
    <div>
      <div class="result">
        <div class="lbl">1위</div>
        <div class="val">{top_brand}</div>
        <div class="dist">거리 {top_dist:.3f}</div>
      </div>
      <div class="blist">{rows}</div>
    </div>
  </div>
  <footer>tools/classify_brand.py predict &middot; Set A(tone+color+gamut)만 사용, texture 미지원<br>
  10개 브랜드 852장 population 시그니처 기준 leave-one-out nearest-centroid</footer>
</div>
</body></html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description="브랜드 시그니처 판별기 - leave-one-out 결정력 검증 / 새 사진 브랜드 순위(재미용)")
    parser.add_argument("--features", choices=["tone_color_gamut", "all"], default="tone_color_gamut",
                         help="tone_color_gamut(기본, Set A) 또는 all(Set B, texture 포함) - report 모드에만 적용")
    parser.add_argument("--csv", default=None, help="confusion matrix를 CSV로도 저장 - report 모드에만 적용")

    subparsers = parser.add_subparsers(dest="command")
    predict_parser = subparsers.add_parser(
        "predict", help="새 사진 하나를 10개 브랜드 centroid와 비교해서 거리 순위 매김(재미용, Set A만 지원)"
    )
    predict_parser.add_argument("photo", help="입력 사진 파일 경로")
    predict_parser.add_argument("--html", default=None, help="자기완결적 HTML 리포트 저장 경로")

    args = parser.parse_args()

    if args.command == "predict":
        ranking = run_predict(args.photo)
        print_predict_report(ranking)
        if args.html:
            write_predict_html(args.photo, ranking, args.html)
            print(f"\n저장됨: {args.html}")
        return

    print(
        f"note: ricoh_gr excluded - color_signature.json uses hue_median instead of "
        f"hue_mean, not comparable to the other {len(CLASSIFIED_BRANDS)} brands' hue feature"
    )
    matrix, report = run(args.features)
    print_report(matrix, report, args.features)
    if args.csv:
        write_csv(matrix, args.csv)
        print(f"\n저장됨: {args.csv}")


if __name__ == "__main__":
    main()
