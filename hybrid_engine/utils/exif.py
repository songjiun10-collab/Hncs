"""EXIF Make/Model 추출 - exiftool 서브프로세스 래퍼. main.py(RAW 입력)와
convert.py(JPEG 입력) 양쪽에서 카메라 자동인식에 쓴다."""
import json
import subprocess


def read_make_model(path):
    out = subprocess.run(["exiftool", "-json", "-Make", "-Model", path],
                          capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    d = data[0] if data else {}
    return d.get("Make"), d.get("Model")
