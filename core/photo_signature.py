"""임의의 사진 한 장에서 datasets/*/{tone,color,gamut}_signature.json과
같은 필드로 시그니처를 계산한다 - "재미용" 브랜드 예측기
(tools/classify_brand.py predict)의 입력 전처리 단계.

texture 필드는 계산하지 않는다 - 브랜드별 sharpening/micro_contrast
계산 공식이 원본 스크립트 유실로 서로 달라져 있다는 게 이미 문서화된
문제라(docs/project_structure.md 참고), 새 사진에 대해 "그 브랜드가
실제로 쓴 공식"을 재현할 방법이 없다.

각 필드의 정의는 tone_signature.json/color_signature.json/
gamut_signature.json의 methodology 필드에 문서화된 걸 그대로
재구현한 것이다 - 원본 계산 스크립트 자체를 복원한 게 아니라 근사
재구현이므로, 기존 population 데이터와 100% 동일한 공식이라는
보장은 없다(설계 근거:
docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md).

hue_mean은 기존 데이터와 같은 단위(OpenCV 원본 H 채널, 0~179 - 실제
색상각의 절반)로 반환한다 - datasets/*/color_signature.json의 실측값이
전부 이 범위(관측된 최댓값 179) 안에 있음을 확인하고 맞췄다. 원형평균
자체는 실제 색상각 단위(0~360도, H*2)로 계산해서 wraparound을 올바르게
처리한 뒤 다시 절반으로 접어 저장 단위에 맞춘다."""
import cv2
import numpy as np


def compute_signature(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

    b2 = float(np.percentile(gray, 2))
    w995 = float(np.percentile(gray, 99.5))
    median = float(np.median(gray))
    dark_pct = float((gray < 40).sum() / gray.size * 100)

    h_raw = hsv[:, :, 0].astype(np.float64)  # OpenCV H, 0~179
    s = hsv[:, :, 1].astype(np.float64)
    mask = s > 20
    sat_mean = float(s[mask].mean()) if mask.any() else 0.0
    if mask.any():
        true_deg = h_raw[mask] * 2.0  # 0~179 -> 실제 0~358도로 펼침
        rad = np.deg2rad(true_deg)
        mean_true_deg = np.degrees(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360.0
        hue_mean = float(mean_true_deg / 2.0)  # 다시 0~179 단위로 접어서 기존 데이터와 단위 일치
    else:
        hue_mean = 0.0

    a = lab[:, :, 1].astype(np.float64)
    b = lab[:, :, 2].astype(np.float64)
    chroma = np.sqrt((a - 128.0) ** 2 + (b - 128.0) ** 2)

    return {
        "b2": b2, "w995": w995, "median": median, "dark_pct": dark_pct,
        "sat_mean": sat_mean, "hue_mean": hue_mean,
        "a_p1": float(np.percentile(a, 1)), "a_p99": float(np.percentile(a, 99)),
        "b_p1": float(np.percentile(b, 1)), "b_p99": float(np.percentile(b, 99)),
        "a_std": float(a.std()), "b_std": float(b.std()),
        "chroma_mean": float(chroma.mean()), "chroma_p99": float(np.percentile(chroma, 99)),
    }
