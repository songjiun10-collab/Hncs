"""11개 population-fit 브랜드의 이미 계산된 시그니처(datasets/<brand>/
*_signature.json)만으로 브랜드 판별력을 검증하는 연구용 도구.
이 LOO 교차검증 자체는 예측 모드가 아님 - 순수하게 "이 시그니처 데이터가
브랜드를 실제로 구별할 만큼 결정력이 있는가"를 확인하는 게 목적. 설계
근거는 docs/superpowers/specs/2026-07-24-brand-classifier-design.md 참고.
(별도의 "재미용" 예측 경로는 이 파일의 rank_brands_by_distance()가
담당한다 - 새 사진 1장을 훈련 풀 전체 centroid와 비교하는 것으로,
held-out 폴드가 없는 별개 문제다. 설계 근거:
docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md.)

이 모듈 자체는 BRANDS의 11개 브랜드 전부를 다룰 수 있지만, 실제 분류
실행은 tools/classify_brand.py가 ricoh_gr을 제외하고 10개 브랜드로만
돌린다(ricoh_gr의 color_signature.json은 다른 10개 브랜드와 달리
hue_mean이 아니라 hue_median을 저장하고 있어 같은 통계가 아님 -
tools/classify_brand.py의 EXCLUDED_BRANDS 참고)."""
import json
import os

import numpy as np

DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")

BRANDS = [
    "hasselblad", "canon", "leica", "nikon", "olympus", "panasonic",
    "pentax", "phaseone", "ricoh_gr", "sigma", "sony",  # ricoh_gr: see module docstring - excluded by tools/classify_brand.py
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


def extract_features(records, feature_set="tone_color_gamut"):
    """records(load_signatures 반환값)에서 (N, D) 피처 행렬과 피처
    이름 리스트를 만든다. hue_mean은 원형 변수라 (cos, sin) 2차원으로
    변환한다(359도와 1도가 raw z-score로는 최대로 멀게 취급되는 문제를
    피하기 위함). npix/is_portrait/quality/subsampling은 색감과 무관한
    메타데이터라 의도적으로 제외."""
    if feature_set == "tone_color_gamut":
        scalar_fields = TONE_FIELDS + ["sat_mean"] + GAMUT_FIELDS
    elif feature_set == "all":
        scalar_fields = TONE_FIELDS + ["sat_mean"] + GAMUT_FIELDS + TEXTURE_FIELDS
    else:
        raise ValueError(f"알 수 없는 feature_set: {feature_set} (tone_color_gamut 또는 all)")

    feature_names = list(scalar_fields) + ["hue_cos", "hue_sin"]
    rows = []
    for rec in records:
        values = [float(rec[field]) for field in scalar_fields]
        hue_rad = np.deg2rad(rec["hue_mean"])
        values.append(float(np.cos(hue_rad)))
        values.append(float(np.sin(hue_rad)))
        rows.append(values)
    X = np.array(rows, dtype=np.float64).reshape(-1, len(feature_names))
    return X, feature_names


def standardize(train_X, vector):
    """train_X의 열별 평균/표준편차로 vector를 z-score 표준화. 표준편차가
    0인 열(분산 없는 피처)은 나눗셈 대신 0을 반환 - 판별에 기여할 정보가
    없는 피처로 취급."""
    mean = train_X.mean(axis=0)
    std = train_X.std(axis=0)
    std_safe = np.where(std == 0, 1.0, std)
    z = (vector - mean) / std_safe
    return np.where(std == 0, 0.0, z)


def nearest_centroid_loo(X, y):
    """leave-one-out 표준화 거리 nearest-centroid 분류. 매 폴드마다
    held-out 샘플 i를 표준화 기준 통계와 자기 브랜드 centroid 양쪽에서
    완전히 제외한다(리키지 방지 - test_excludes_held_out_sample_from_own_
    brand_centroid 참고)."""
    y = np.asarray(y)
    n = X.shape[0]
    predictions = np.empty(n, dtype=y.dtype)
    all_indices = np.arange(n)

    for i in range(n):
        keep = all_indices != i
        train_X = X[keep]
        train_y = y[keep]
        z = standardize(train_X, X[i])

        best_brand = None
        best_dist = None
        for brand in np.unique(train_y):
            centroid_raw = train_X[train_y == brand].mean(axis=0)
            centroid_z = standardize(train_X, centroid_raw)
            dist = float(np.linalg.norm(z - centroid_z))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_brand = brand
        predictions[i] = best_brand

    return predictions


def rank_brands_by_distance(query_vector, train_X, train_y):
    """query_vector(D,)가 train_X/train_y(전체 훈련 풀, held-out 없음)
    기준으로 각 브랜드 centroid와 표준화 공간에서 얼마나 가까운지
    오름차순으로 정렬해서 반환. nearest_centroid_loo()와 달리 폴드마다
    제외할 대상이 없다 - query_vector는 애초에 train_X에 속하지 않는
    새로운 사진이라 리키지 문제 자체가 없다."""
    train_y = np.asarray(train_y)
    z = standardize(train_X, query_vector)
    ranking = []
    for brand in np.unique(train_y):
        centroid_raw = train_X[train_y == brand].mean(axis=0)
        centroid_z = standardize(train_X, centroid_raw)
        dist = float(np.linalg.norm(z - centroid_z))
        ranking.append((str(brand), dist))
    ranking.sort(key=lambda pair: pair[1])
    return ranking


def confusion_matrix(y_true, y_pred, brands=BRANDS):
    """brands 순서로 정렬된 (len(brands), len(brands)) confusion matrix.
    matrix[i, j] = 실제 브랜드가 brands[i]인데 brands[j]로 예측된 개수."""
    index = {b: i for i, b in enumerate(brands)}
    matrix = np.zeros((len(brands), len(brands)), dtype=int)
    for true_label, pred_label in zip(y_true, y_pred):
        matrix[index[true_label], index[pred_label]] += 1
    return matrix


def classification_report(y_true, y_pred, brands=BRANDS):
    """브랜드별 precision/recall/f1/표본수와 두 baseline(다수결,
    균등확률), 그리고 전체 정확도(accuracy)와 브랜드별 recall의 비가중
    평균(macro_accuracy = balanced accuracy, 표본 불균형에 영향받지
    않음)을 담은 딕셔너리를 반환."""
    matrix = confusion_matrix(y_true, y_pred, brands=brands)

    per_brand = {}
    for i, brand in enumerate(brands):
        n = int(matrix[i].sum())
        tp = int(matrix[i, i])
        predicted_as_brand = int(matrix[:, i].sum())
        recall = tp / n if n > 0 else 0.0
        precision = tp / predicted_as_brand if predicted_as_brand > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        per_brand[brand] = {"precision": precision, "recall": recall, "f1": f1, "n": n}

    total = int(matrix.sum())
    accuracy = float(np.trace(matrix)) / total if total > 0 else 0.0
    macro_accuracy = float(np.mean([per_brand[b]["recall"] for b in brands]))
    counts = matrix.sum(axis=1)
    majority_baseline = float(counts.max()) / total if total > 0 else 0.0
    uniform_baseline = 1.0 / len(brands)

    return {
        "per_brand": per_brand,
        "accuracy": accuracy,
        "macro_accuracy": macro_accuracy,
        "majority_baseline": majority_baseline,
        "uniform_baseline": uniform_baseline,
    }
