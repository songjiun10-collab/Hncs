"""EXIF Make/Model 추출 - exiftool 서브프로세스 래퍼. main.py(RAW 입력)와
convert.py(JPEG 입력) 양쪽에서 카메라 자동인식에 쓴다."""
import json
import subprocess

import numpy as np


def read_make_model(path):
    out = subprocess.run(["exiftool", "-json", "-Make", "-Model", path],
                          capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    d = data[0] if data else {}
    return d.get("Make"), d.get("Model")


def read_unique_camera_model(path):
    """DNG/DCP의 UniqueCameraModel 태그를 읽는다 - DCP 프로필이 "이
    프로필은 어느 카메라용인가"를 선언하는 데 쓰는 값. 태그가 없으면
    Make + Model을 공백으로 이어 붙여 대체하고, 둘 다 없으면 None."""
    out = subprocess.run(
        ["exiftool", "-json", "-UniqueCameraModel", "-Make", "-Model", path],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    d = data[0] if data else {}
    unique = d.get("UniqueCameraModel")
    if unique:
        return unique
    make, model = d.get("Make"), d.get("Model")
    if make and model:
        return f"{make} {model}"
    return model or make or None


def read_as_shot_neutral(path):
    """AsShotNeutral 태그(촬영 당시 중립색의 카메라 네이티브 RGB 값,
    DNG 스펙 정의)를 (3,) float 배열로 읽는다. 없으면 None.

    exiftool은 이 값을 "0.3688 1 0.5917" 같은 공백 구분 문자열로
    준다."""
    out = subprocess.run(
        ["exiftool", "-json", "-AsShotNeutral", path],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    raw_value = (data[0] if data else {}).get("AsShotNeutral")
    if not raw_value:
        return None
    parts = str(raw_value).replace(",", " ").split()
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    return np.array(values[:3], dtype=np.float64) if len(values) >= 3 else None
