"""`datasets/hasselblad/contributed/local-mixed-2026-07/`가 (원인 불명,
이번 세션 시작 전부터 커밋 안 된 채로) 통째로 디스크에서 사라진 걸 발견 -
manifest.csv의 download_url이 전부 "local (owner personal library)"라
git으로도 복구 불가능했다. 사용자 확인: 원본이 애초에 dpreview 샘플
갤러리였으니 그냥 다시 받으면 된다.

tools/dpreview_x1d_x2d100c_links.csv(X1D 52 + X2D 100C 112 = 164쌍, 원래
61쌍보다 많음 - dpreview 갤러리가 그새 늘어남)를 받아서
`datasets/hasselblad/contributed/x1d-x2d100c-restore-2026-08/`로 정리.
다운로드 메커니즘은 tools/download_xcd_lens_gallery.py와 동일 - JPG는 curl,
RAW(.3fr)는 Cloudflare 우회를 위해 OpenCLI 로그인 브라우저로 navigate.

  python3 -m tools.download_x1d_x2d100c_restore
"""
import csv
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dpreview_x1d_x2d100c_links.csv")
SET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "hasselblad", "contributed", "x1d-x2d100c-restore-2026-08")
DOWNLOADS = os.path.expanduser("~/Downloads")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _download_jpg(url, dest):
    subprocess.run(["curl", "-sL", "-A", UA, "-o", dest, url], check=True, timeout=60)


def _download_raw_via_browser(url, filename, dest, timeout=30):
    dl_path = os.path.join(DOWNLOADS, filename)
    if os.path.exists(dl_path):
        os.remove(dl_path)
    subprocess.run(["opencli", "browser", "main", "open", url],
                    capture_output=True, timeout=30)
    waited = 0
    while waited < timeout:
        if os.path.exists(dl_path) and os.path.getsize(dl_path) > 1_000_000:
            size1 = os.path.getsize(dl_path)
            time.sleep(1)
            if os.path.exists(dl_path) and os.path.getsize(dl_path) == size1:
                os.rename(dl_path, dest)
                return True
        time.sleep(1)
        waited += 1
    return False


def _exif(path, tags):
    import json
    out = subprocess.run(["exiftool", "-json"] + [f"-{t}" for t in tags] + [path],
                          capture_output=True, text=True, timeout=30)
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    return json.loads(out.stdout)[0]


def main():
    os.makedirs(os.path.join(SET_DIR, "raw"), exist_ok=True)
    os.makedirs(os.path.join(SET_DIR, "jpeg"), exist_ok=True)
    manifest_path = os.path.join(SET_DIR, "manifest.csv")
    write_header = not os.path.exists(manifest_path)

    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"총 {len(rows)}쌍 처리 시작")

    manifest_f = open(manifest_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(manifest_f, fieldnames=[
        "filename_raw", "filename_jpeg", "camera", "lens", "iso", "wb_setting",
        "scene_type", "filename_phocus_tiff", "phocus_settings", "illuminant",
        "download_url", "notes"])
    if write_header:
        writer.writeheader()

    ok, fail = 0, 0
    for i, row in enumerate(rows):
        gallery_label = row["lens"]  # CSV 컬럼명은 재사용이지만 실제 값은 바디명
        jpg_url, raw_url = row["jpg_url"], row["raw_url"]
        jpg_name = os.path.basename(jpg_url)
        raw_name = os.path.basename(raw_url)
        jpg_dest = os.path.join(SET_DIR, "jpeg", jpg_name)
        raw_dest = os.path.join(SET_DIR, "raw", raw_name)

        print(f"[{i + 1}/{len(rows)}] {gallery_label}: {raw_name}", flush=True)
        try:
            if not os.path.exists(jpg_dest):
                _download_jpg(jpg_url, jpg_dest)
            if not os.path.exists(raw_dest):
                got = _download_raw_via_browser(raw_url, raw_name, raw_dest)
                if not got:
                    print("    RAW 다운로드 타임아웃, 스킵")
                    fail += 1
                    continue

            meta = _exif(raw_dest, ["Model", "LensModel", "ISO", "WhiteBalance", "DateTimeOriginal"])
            writer.writerow({
                "filename_raw": raw_name,
                "filename_jpeg": jpg_name,
                "camera": meta.get("Model", gallery_label),
                "lens": meta.get("LensModel", "unknown"),
                "iso": meta.get("ISO", ""),
                "wb_setting": meta.get("WhiteBalance", ""),
                "scene_type": "",
                "filename_phocus_tiff": "",
                "phocus_settings": "",
                "illuminant": "",
                "download_url": raw_url,
                "notes": f"dpreview {gallery_label} 샘플 갤러리 (local-mixed-2026-07 소실분 복구)",
            })
            manifest_f.flush()
            ok += 1
        except Exception as e:
            print(f"    실패: {e}")
            fail += 1

    manifest_f.close()
    print(f"\n완료: {ok}개 성공, {fail}개 실패")


if __name__ == "__main__":
    main()
