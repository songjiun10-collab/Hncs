"""kmichels-x2dii-2026-07 챠트 세트(공식 카메라 네이티브 매트릭스 분석의
근거 데이터)가 로컬에서 유실돼 B_31325 1장만 남아있던 걸(2026-08 세션
기록 참고) manifest.csv에 남아있는 개별 구글 드라이브 URL로 나머지
8장(B_31326~B_31333, raw+jpeg)을 재다운로드해서 복원한다. B_31334는
report JSON엔 있지만 manifest.csv에 URL 자체가 기록된 적이 없어서
복구 불가(누락 - 원래 커밋부터 9행뿐이었음, `git log`로 확인).

구글 드라이브 대용량(가상 스캔 경고) 파일은 curl 단순 GET으로 안 되고
interstitial HTML의 confirm/uuid 폼 필드를 읽어서 재요청해야 한다
(`https://drive.usercontent.google.com/download?id=...&export=download&confirm=t&uuid=...`).

  python3 -m tools.recover_kmichels_x2dii_chart
"""
import csv
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
MANIFEST = os.path.join(SET_DIR, "manifest.csv")


def _extract_id(drive_url):
    m = re.search(r"/file/d/([^/]+)/", drive_url)
    return m.group(1) if m else None


def _download_drive_file(file_id, dest):
    raw_bytes = subprocess.run(
        ["curl", "-sL", f"https://drive.google.com/uc?export=download&id={file_id}"],
        capture_output=True, timeout=60).stdout
    text = raw_bytes.decode("utf-8", errors="ignore")
    confirm = re.search(r'name="confirm" value="([^"]+)"', text)
    uuid = re.search(r'name="uuid" value="([^"]+)"', text)
    if confirm and uuid:
        url = (f"https://drive.usercontent.google.com/download?id={file_id}"
               f"&export=download&confirm={confirm.group(1)}&uuid={uuid.group(1)}")
        subprocess.run(["curl", "-sL", url, "-o", dest], check=True, timeout=300)
    else:
        # 작은 파일은 interstitial 없이 바로 받아짐 - 응답 바이트를 그대로 저장
        with open(dest, "wb") as f:
            f.write(raw_bytes)


def main():
    os.makedirs(os.path.join(SET_DIR, "raw"), exist_ok=True)
    os.makedirs(os.path.join(SET_DIR, "jpeg"), exist_ok=True)
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    print(f"manifest {len(rows)}행", flush=True)

    for row in rows:
        raw_name = row["filename_raw"]
        jpg_name = row["filename_jpeg"]
        raw_dest = os.path.join(SET_DIR, "raw", raw_name)
        jpg_dest = os.path.join(SET_DIR, "jpeg", jpg_name)

        raw_url = row["download_url"]
        jpg_m = re.search(r"JPEG:\s*(https://drive\.google\.com/file/d/[^\s]+)", row["notes"])
        jpg_url = jpg_m.group(1) if jpg_m else None

        if not os.path.exists(raw_dest) or os.path.getsize(raw_dest) < 1_000_000:
            raw_id = _extract_id(raw_url)
            print(f"  {raw_name} 다운로드 중...", flush=True)
            _download_drive_file(raw_id, raw_dest)
            print(f"    {os.path.getsize(raw_dest) / 1e6:.1f}MB")
        else:
            print(f"  {raw_name} 이미 있음, 스킵")

        if jpg_url and (not os.path.exists(jpg_dest) or os.path.getsize(jpg_dest) < 100_000):
            jpg_id = _extract_id(jpg_url)
            print(f"  {jpg_name} 다운로드 중...", flush=True)
            _download_drive_file(jpg_id, jpg_dest)
            print(f"    {os.path.getsize(jpg_dest) / 1e6:.1f}MB")
        elif os.path.exists(jpg_dest):
            print(f"  {jpg_name} 이미 있음, 스킵")
        else:
            print(f"  {jpg_name}: JPEG URL을 notes에서 못 찾음")

    print("\n완료. raw/jpeg 폴더 확인 필요.")


if __name__ == "__main__":
    main()
