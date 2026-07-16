"""
"이 이미지가 진짜 미가공 SOOC인가" / "이 변환이 hue를 보존하는가" /
"이 파일이 실제로 온전히 디코드되는가" 검증 헬퍼. tools/analyze.py의
라이카/Phase One/Pentax/Ricoh GR 스크레이핑 로직과 portrait_skin_analysis
로직에서 거의 동일하게 중복돼 있던 걸 합쳤다.

2026-07: imaging-resource.com에서 받은 Hasselblad(X1D/X2D 100C 갤러리
72% 손상), Phase One(30/30 전부 손상), Pentax(40장 중 16장 손상) 이미지가
같은 파일을 몇 번을 다시 받아도(다른 다운로드 방식으로도) 정확히 같은
지점부터 세로로 텅 빈 상태로 잘려있는 걸 확인 - 전송 문제가 아니라
media.imaging-resource.com에 저장된 원본 파일 자체가 손상돼 있는
것(연도 상관없이 여러 갤러리에 걸친 사이트 자체의 고질적 문제로 보임).
OpenCV(cv2.imread)는 이런 파일도 "Premature end of JPEG file" 경고만
띄우고 나머지를 0으로 채운 채 조용히 디코드에 "성공"해버려서, shape나
로드 성공 여부만으로는 못 거른다 - is_image_usable()로 행 단위 분산을
봐야 걸러짐. 이후 모든 브랜드 population 분석은 이 함수를 통과한
이미지만 쓰기로 함(README/각 브랜드 docstring 참고).
"""
import subprocess

import cv2
import numpy as np


def is_image_array_usable(img, max_degenerate_row_frac=0.02):
    """행(row) 단위 표준편차가 거의 0인(=텅 빈/손상된) 행의 비율이
    max_degenerate_row_frac을 넘으면 손상으로 간주. imaging-resource.com
    CDN에서 실측된 손상 패턴(디코드가 중간에 멈추고 나머지가 검은/단색
    행으로 남는 형태)에 맞춘 검증 - EOI 마커 유무나 cv2 로드 성공 여부만
    보는 것보다 훨씬 신뢰도가 높다(위 모듈 docstring 참고)."""
    if img is None:
        return False
    h, w = img.shape[:2]
    if h < 100 or w < 100:
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    row_std = gray.std(axis=1)
    degenerate_frac = (row_std < 0.5).sum() / len(row_std)
    return degenerate_frac <= max_degenerate_row_frac


def is_image_usable(path, max_degenerate_row_frac=0.02):
    """is_image_array_usable()의 파일 경로 버전."""
    return is_image_array_usable(cv2.imread(path), max_degenerate_row_frac)


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
