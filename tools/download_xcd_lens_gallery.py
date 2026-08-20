"""tools/dpreview_xcd_lens_links.csv(하셀블라드 XCD 렌즈 5개, dpreview 샘플
갤러리 145쌍)를 실제로 받아서 datasets/hasselblad/contributed/xcd-lenses-2026-08/
로 정리하는 원샷 스크립트.

JPG는 Cloudflare 차단이 없어서 curl로 바로 받지만, RAW(.3fr)는 봇 차단이
걸려있어서 OpenCLI가 붙잡고 있는 실제 로그인 브라우저로 그 URL을
`open`(navigate)해야 진짜 브라우저 다운로드로 ~/Downloads에 떨어진다(테스트
확인, 2026-08). 그래서 RAW 한 장마다 opencli 서브프로세스를 부른다 - 느리지만
(장당 몇 초) 145장이면 감당 가능한 수준.

  python3 -m tools.download_xcd_lens_gallery
"""
import csv
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dpreview_xcd_lens_links.csv")
SET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "hasselblad", "contributed", "xcd-lenses-2026-08")
DOWNLOADS = os.path.expanduser("~/Downloads")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _download_jpg(url, dest):
    subprocess.run(["curl", "-sL", "-A", UA, "-o", dest, url], check=True, timeout=60)


def _download_raw_via_browser(url, filename, dest, timeout=30):
    dl_path = os.path.join(DOWNLOADS, filename)
    if os.path.exists(dl_path):
        os.remove(dl_path)  # 이전 잔여물이면 새로 받은 게 맞는지 확인 못 하니 지우고 다시
    subprocess.run(["opencli", "browser", "main", "open", url],
                    capture_output=True, timeout=30)
    waited = 0
    while waited < timeout:
        if os.path.exists(dl_path) and os.path.getsize(dl_path) > 1_000_000:
            # Chrome이 .crdownload로 쓰다가 완료시 rename - 크기 안정화까지 확인
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
        lens = row["lens"]
        jpg_url, raw_url = row["jpg_url"], row["raw_url"]
        jpg_name = os.path.basename(jpg_url)
        raw_name = os.path.basename(raw_url)
        jpg_dest = os.path.join(SET_DIR, "jpeg", jpg_name)
        raw_dest = os.path.join(SET_DIR, "raw", raw_name)

        print(f"[{i + 1}/{len(rows)}] {lens}: {raw_name}", flush=True)
        try:
            if not os.path.exists(jpg_dest):
                _download_jpg(jpg_url, jpg_dest)
            if not os.path.exists(raw_dest):
                got = _download_raw_via_browser(raw_url, raw_name, raw_dest)
                if not got:
                    print("    RAW 다운로드 타임아웃, 스킵")
                    fail += 1
                    continue

            meta = _exif(raw_dest, ["Model", "ISO", "WhiteBalance", "DateTimeOriginal"])
            writer.writerow({
                "filename_raw": raw_name,
                "filename_jpeg": jpg_name,
                "camera": meta.get("Model", ""),
                "lens": lens,
                "iso": meta.get("ISO", ""),
                "wb_setting": meta.get("WhiteBalance", ""),
                "scene_type": "",
                "filename_phocus_tiff": "",
                "phocus_settings": "",
                "illuminant": "",
                "download_url": raw_url,
                "notes": f"dpreview XCD 렌즈 샘플 갤러리 ({lens})",
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
