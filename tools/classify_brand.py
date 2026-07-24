"""브랜드 시그니처 판별기 CLI - 11개 브랜드의 이미 계산된 population
시그니처(datasets/*/*_signature.json)만으로 leave-one-out 교차검증 기반
nearest-centroid 분류를 돌려서 confusion matrix와 지표를 출력한다.
연구용 검증 도구 - 새 사진을 넣어 예측하는 기능은 없음
(docs/superpowers/specs/2026-07-24-brand-classifier-design.md 참고)."""
import argparse
import csv

import numpy as np

from core.brand_classifier import (
    BRANDS, load_signatures, extract_features, nearest_centroid_loo,
    confusion_matrix, classification_report,
)

# datasets/ricoh_gr/color_signature.json stores hue_median instead of
# hue_mean (the only one of the 11 brands that does), so its hue feature
# isn't computed on the same basis as the other 10 brands' - including it
# would let the classifier partly key off a data-collection artifact
# instead of a genuine color-rendering difference.
EXCLUDED_BRANDS = {"ricoh_gr"}

CLASSIFIED_BRANDS = [b for b in BRANDS if b not in EXCLUDED_BRANDS]


def run(feature_set):
    all_X = []
    all_y = []
    for brand in BRANDS:
        if brand in EXCLUDED_BRANDS:
            continue
        records = load_signatures(brand)
        X, _ = extract_features(records, feature_set=feature_set)
        all_X.append(X)
        all_y.extend([brand] * len(records))
    X = np.concatenate(all_X, axis=0)
    y = np.array(all_y)

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


def main():
    parser = argparse.ArgumentParser(description="브랜드 시그니처 판별기 - leave-one-out 결정력 검증")
    parser.add_argument("--features", choices=["tone_color_gamut", "all"], default="tone_color_gamut",
                         help="tone_color_gamut(기본, Set A) 또는 all(Set B, texture 포함)")
    parser.add_argument("--csv", default=None, help="confusion matrix를 CSV로도 저장")
    args = parser.parse_args()

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
