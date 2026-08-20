"""
population 통계 계산 - tools/analyze.py의 모든 브랜드 분석에서 동일하게
쓰던 stats()가 analyze_all_samples.py/analyze_leica_samples.py/
analyze_phaseone_samples.py/analyze_pentax_samples.py/
analyze_ricoh_gr_samples.py/analyze_fuji_film_modes.py에 5~6번 그대로
중복돼 있던 걸 하나로 합쳤다.
"""
import cv2
import numpy as np


def image_stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    p = np.percentile
    dark = (gray < 40).sum() / gray.size * 100
    return dict(
        b2=p(gray, 2), w995=p(gray, 99.5), med=np.median(gray),
        sat=s[s > 20].mean() if (s > 20).any() else 0, dark_pct=dark,
    )
