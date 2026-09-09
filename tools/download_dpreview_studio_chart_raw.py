"""7개 브랜드(canon/nikon/panasonic/sigma/ricoh_gr/olympus/pentax) 스튜디오
챠트 RAW 재다운로드 - `tools/dpreview/write_dpreview_manifest.py`가 디스크 확보용으로
raw/ 를 지운 뒤 manifest.csv(image_id, camera, product_id, raw_file_url)만
남았고, dpreview.com RAW URL이 Cloudflare managed challenge라 `curl`/샌드박스
브라우저 pane 둘 다 막혀있었다(`hybrid_engine/EVALUATION.md` 참고). opencli의
Browser Bridge(사용자 실제 Chrome, 로그인된 세션)가 이 챌린지를 통과하는
걸 2026-09-06에 확인해서 그 경로로 재다운로드한다.

manifest.csv의 raw_file_url 마지막 경로 조각(해시.확장자)이 다운로드
파일명 그대로라 `tools/dpreview/match_dpreview_downloads_by_hash.py`의 SHA-256
매칭(익명화된 blob 다운로드 전용, 샌드박스 pane에서만 필요)이 기본적으로
필요 없다 - opencli는 실제 파일명을 그대로 ~/Downloads에 내려받는다.
단, manifest에 `sha256` 열이 있으면 기존 raw를 그 해시가 일치할 때만
재사용한다. 해시가 없으면 기존 파일도 다시 받아 provenance를 확인한다.

  ~/.nvm/versions/node/v22.22.1/bin/opencli browser main open <url>  (1건 예시)
  python3 -m tools.download_dpreview_studio_chart_raw <manifest.csv> <raw_dir>
"""
import csv
import hashlib
import os
import subprocess
import sys
import time

DOWNLOADS = os.path.expanduser("~/Downloads")
OPENCLI = os.path.expanduser("~/.nvm/versions/node/v22.22.1/bin/opencli")


def _wait_for_download(fname, timeout_s=90, poll_s=1.0):
    """다운로드가 끝날 때까지 기다린다 - Chrome은 진행 중엔 `<fname>.crdownload`로
    쓰다가 완료 시 실제 이름으로 rename하므로 그 임시파일이 사라지고 최종
    파일이 나타나는 시점을 본다."""
    dest = os.path.join(DOWNLOADS, fname)
    partial = dest + ".crdownload"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if (os.path.exists(dest) and os.path.getsize(dest) > 0
                and not os.path.exists(partial)):
            return dest
        time.sleep(poll_s)
    return None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quarantine_stale_download(path):
    if not os.path.exists(path):
        return
    candidate = path + ".hncs-stale"
    suffix = 1
    while os.path.exists(candidate):
        candidate = f"{path}.hncs-stale.{suffix}"
        suffix += 1
    os.replace(path, candidate)


def download_manifest(manifest_csv, raw_dir, session="main", timeout_s=90):
    os.makedirs(raw_dir, exist_ok=True)
    with open(manifest_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    ok, failed = [], []
    for i, row in enumerate(rows):
        url = row["raw_file_url"]
        fname = os.path.basename(url)
        dest = os.path.join(raw_dir, fname)
        expected_sha256 = row.get("sha256", "").strip().lower()
        if (expected_sha256 and os.path.exists(dest)
                and os.path.getsize(dest) > 0
                and _sha256(dest) == expected_sha256):
            ok.append(fname)
            print(f"  [{i + 1}/{len(rows)}] {fname}: SHA-256 일치, 건너뜀")
            continue

        # A previous failed attempt may have left a same-named file in the
        # browser download directory. Never let that file satisfy this run.
        stale_src = os.path.join(DOWNLOADS, fname)
        _quarantine_stale_download(stale_src)
        try:
            result = subprocess.run(
                [OPENCLI, "browser", session, "open", url],
                capture_output=True, text=True, timeout=timeout_s,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            failed.append(fname)
            print(f"  [{i + 1}/{len(rows)}] {fname}: opencli 실패 ({type(exc).__name__})")
            continue
        if result.returncode != 0:
            failed.append(fname)
            detail = (result.stderr or "").strip()
            suffix = f": {detail}" if detail else ""
            print(f"  [{i + 1}/{len(rows)}] {fname}: opencli 실패{suffix}")
            continue
        src = _wait_for_download(fname, timeout_s=timeout_s)
        if src is None:
            failed.append(fname)
            print(f"  [{i + 1}/{len(rows)}] {fname}: 다운로드 실패/타임아웃")
            continue
        os.replace(src, dest)
        ok.append(fname)
        print(f"  [{i + 1}/{len(rows)}] {fname}: OK ({os.path.getsize(dest) / 1e6:.1f}MB)")

    print(f"\n{manifest_csv}: 성공 {len(ok)}/{len(rows)}, 실패 {len(failed)}")
    if failed:
        print(f"  실패 목록: {failed}")
    return ok, failed


if __name__ == "__main__":
    download_manifest(sys.argv[1], sys.argv[2])
