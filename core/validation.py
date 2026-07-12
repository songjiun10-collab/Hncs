"""
"이 이미지가 진짜 미가공 SOOC인가" / "이 변환이 hue를 보존하는가" 검증
헬퍼. tools/analyze.py의 라이카/Phase One/Pentax/Ricoh GR 스크레이핑
로직과 portrait_skin_analysis 로직에서 거의 동일하게 중복돼 있던 걸
합쳤다.
"""
import subprocess

import cv2
import numpy as np


def genuine_render_check(path, expected_keywords, reject_keywords):
    """
    EXIF Make/Software 텍스트에 (1) 기대하는 브랜드/렌더러 키워드가 있는지,
    (2) 제3자 편집(Photoshop/Lightroom 등) 키워드가 있는지 확인.
    브랜드마다 "기대값"이 다르다 - 예: Phase One은 Software="Capture One"이
    있어야 정상(자사 RAW 컨버터)이지만, 라이카/펜탁스/리코는 Capture One이
    있으면 오히려 제3자 편집으로 취급해야 함.
    반환: (expected_ok, rejected)
    """
    out = subprocess.run(["exiftool", "-Make", "-Software", path],
                          capture_output=True, timeout=30)
    text = out.stdout.decode("utf-8", errors="ignore").lower()
    expected_ok = any(k in text for k in expected_keywords)
    rejected = any(k in text for k in reject_keywords)
    return expected_ok, rejected


def region_hue(img_bgr, box, margin=(0.3, 0.25, 0.7, 0.55)):
    """box(x, y, w, h) 안쪽 margin 비율 영역(기본: 얼굴 bbox 중앙 40%,
    이마/뺨 위주로 눈/입 제외)의 평균 hue."""
    x, y, w, h = box
    m0x, m0y, m1x, m1y = margin
    cx0, cy0 = x + int(w * m0x), y + int(h * m0y)
    cx1, cy1 = x + int(w * m1x), y + int(h * m1y)
    patch = img_bgr[cy0:cy1, cx0:cx1]
    if patch.size == 0:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    return float(np.median(hsv[:, :, 0]))
