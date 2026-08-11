"""
로컬 사진 라이브러리(원본 폴더에 raw+jpeg가 뒤섞여 있는 상태)에서
EXIF DateTimeOriginal로 raw+jpeg 페어를 찾아 datasets/<브랜드>/contributed/
<세트>/manifest.csv에 추가하고, tools.verify_contributed_pairs의 verify_row로
바로 재검증해서 FAIL 행(대부분 Lightroom/Photoshop 편집본, 또는 셔터 비동기)을
자동으로 제거하는 CLI. manifest.csv에는 항상 PASS한 행만 남는다.

  python3 -m tools.build_local_manifest ~/Downloads datasets/hasselblad/contributed/local-mixed-2026-07
  python3 -m tools.build_local_manifest ~/Downloads datasets/leica/contributed/<세트> --make Leica

--make 기본값은 Hasselblad(기존 호출 하위호환) - drop_failed() 단계에서
verify_row()에 그대로 넘겨 EXIF Make 대조에 쓴다.

같은 셔터의 raw/jpeg인데도 DateTimeOriginal이 정수 시간 단위로 어긋나는
카메라/펌웨어가 있었다(2017년 X1D 파일 일부 - raw가 jpeg보다 정확히 7시간
빠르게 기록됨, 분·초는 완전히 일치). 이런 경우를 놓치지 않도록 ±12시간
정수 오프셋도 함께 탐색한다 - 분·초까지 우연히 일치할 확률은 사실상 0이라
오프셋이 걸리면 안전한 매칭으로 간주한다.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta

# .3fr/.fff=Hasselblad, .dng=Leica(M/SL/Q 전 라인업 공식 RAW 포맷)/Sigma,
# .arw=Sony, .cr3=Canon, .raf=Fujifilm, .nef=Nikon
RAW_EXT = {".3fr", ".fff", ".dng", ".arw", ".cr3", ".raf", ".nef"}
JPEG_EXT = {".jpg", ".jpeg"}
OFFSET_HOURS = list(range(-12, 13))
COLUMNS = ["filename_raw", "filename_jpeg", "camera", "lens", "iso", "wb_setting",
           "scene_type", "filename_phocus_tiff", "phocus_settings", "illuminant",
           "download_url", "notes"]


def _exiftool_batch(paths):
    if not paths:
        return []
    out = subprocess.run(
        ["exiftool", "-json", "-DateTimeOriginal", "-Make", "-Model", "-LensModel", "-ISO",
         "-FileName"] + paths,
        capture_output=True, text=True, timeout=600)
    return json.loads(out.stdout) if out.stdout.strip() else []


def _parse_dt(v):
    if not v:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(v)[:19], fmt)
        except ValueError:
            continue
    return None


def _norm_camera(model):
    model = (model or "").strip()
    return "Hasselblad X1D" if model == "X1D" else (model or "unknown")


def _classify_scene(iso):
    try:
        return "daylight" if int(iso) <= 200 else "lowlight"
    except (ValueError, TypeError):
        return "daylight"


def _match_pairs(raws, jpegs):
    """raws/jpegs(각 {filename, dt, ...} dict 리스트)를 1:1 deterministic
    매칭한다 - (raw_rec, jpeg_rec, delta_s, offset_h) 리스트 반환. 순수
    함수(exiftool/파일시스템 의존 없음)라 합성 fixture로 직접 단위
    테스트할 수 있다.

    **정정(2026-08 코드리뷰)**: 예전 구현은 raw를 시각순으로 하나씩
    처리하면서 그 시점에 jpeg 풀에 "남아있는 순서상 처음 만난" 후보를
    집었다(offset=0을 더 선호하는 것 말고는 델타 크기를 전혀 비교하지
    않음) - 이 풀 순서가 exiftool 배치 호출의 입력 순서, 즉
    `os.listdir()` 순서를 그대로 물려받아 파일시스템/OS에 따라 달라질
    수 있었다. 버스트 촬영(여러 raw+jpeg가 몇 초 안에 몰림)이나 동일초
    타임스탬프처럼 여러 후보가 동시에 매칭 범위에 들어오는 경우, 실제로
    가장 가까운 페어가 아니라 디렉터리 나열 순서가 매칭을 결정해버리는
    비결정적 버그였다.

    지금은 raw x jpeg x offset 전체 후보를 모아서 (offset=0 우선,
    그 다음 델타 오름차순, 그 다음 파일명순 - 마지막 tiebreak가 있어야
    같은 델타의 후보가 여럿이어도 실행마다 같은 결과가 나온다)으로 정렬한
    뒤 그리디로 하나씩 배정한다(이미 쓰인 raw/jpeg는 건너뜀) - 전역
    최적(헝가리안 알고리즘) 은 아니지만 "가장 가까운 후보부터 확정"이라
    직관적으로 맞고, 무엇보다 입력 순서와 무관하게 항상 같은 결과가
    나온다."""
    candidates = []
    for r in raws:
        for j in jpegs:
            for oh in OFFSET_HOURS:
                delta = abs((r["dt"] + timedelta(hours=oh) - j["dt"]).total_seconds())
                if delta <= 2.0:
                    candidates.append((oh != 0, delta, r["filename"], j["filename"], r, j, oh))
                    break  # 이 (r, j) 쌍은 처음 맞는 오프셋 하나만 후보로 등록
    candidates.sort(key=lambda c: c[:4])

    used_raw, used_jpeg = set(), set()
    pairs = []
    for _, delta, _, _, r, j, oh in candidates:
        if r["filename"] in used_raw or j["filename"] in used_jpeg:
            continue
        used_raw.add(r["filename"])
        used_jpeg.add(j["filename"])
        pairs.append((r, j, delta, oh))

    pairs.sort(key=lambda p: (p[0]["dt"], p[0]["filename"]))
    return pairs


def find_pairs(src_dir, already_raw, already_jpeg):
    """src_dir 안의 raw/jpeg 파일을 스캔해서 (raw_rec, jpeg_rec, delta_s, offset_h) 리스트 반환.
    이미 세트에 들어간 파일명(already_raw/already_jpeg)은 후보에서 제외.
    실제 매칭 로직은 _match_pairs() - 여기는 exiftool로 후보 레코드를
    모으기만 한다."""
    all_paths = []
    for fn in os.listdir(src_dir):
        ext = os.path.splitext(fn)[1].lower()
        if ext in RAW_EXT or ext in JPEG_EXT:
            all_paths.append(os.path.join(src_dir, fn))

    exif = _exiftool_batch(all_paths)
    raws, jpegs = [], []
    for e in exif:
        fn = e.get("FileName")
        ext = os.path.splitext(fn)[1].lower()
        dt = _parse_dt(e.get("DateTimeOriginal"))
        if dt is None:
            continue
        rec = dict(filename=fn, dt=dt, model=e.get("Model", ""), lens=e.get("LensModel", ""),
                   iso=e.get("ISO", ""))
        if ext in RAW_EXT and fn not in already_raw:
            raws.append(rec)
        elif ext in JPEG_EXT and fn not in already_jpeg:
            jpegs.append(rec)

    return _match_pairs(raws, jpegs)


def append_manifest(set_dir, pairs, src_dir, download_note):
    os.makedirs(os.path.join(set_dir, "raw"), exist_ok=True)
    os.makedirs(os.path.join(set_dir, "jpeg"), exist_ok=True)
    manifest_path = os.path.join(set_dir, "manifest.csv")
    write_header = not os.path.exists(manifest_path)

    with open(manifest_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()
        for r, j, delta, oh in pairs:
            shutil.copy2(os.path.join(src_dir, r["filename"]),
                         os.path.join(set_dir, "raw", r["filename"]))
            shutil.copy2(os.path.join(src_dir, j["filename"]),
                         os.path.join(set_dir, "jpeg", j["filename"]))
            offset_note = (f", 정수시간 오프셋 {oh:+d}h 보정 적용(분/초 완전일치로 확인)"
                           if oh != 0 else "")
            w.writerow(dict(
                filename_raw=r["filename"], filename_jpeg=j["filename"],
                camera=_norm_camera(r["model"]), lens=r["lens"].strip() or "unknown",
                iso=r["iso"], wb_setting="auto", scene_type=_classify_scene(r["iso"]),
                filename_phocus_tiff="", phocus_settings="", illuminant="",
                download_url=download_note,
                notes=f"exif raw DateTimeOriginal={r['dt']}, jpeg DateTimeOriginal={j['dt']}{offset_note}",
            ))


def drop_failed(set_dir, expected_make="Hasselblad"):
    """manifest.csv 전체를 verify_row로 재검증해서 FAIL 행+파일을 제거하고
    PASS만 남긴다 (verify_contributed_pairs 자체는 리포트만 찍고 정리는
    안 하므로, 두 단계를 한 번에 묶어 재현 가능하게 만든 것)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.verify_contributed_pairs import verify_row

    manifest_path = os.path.join(set_dir, "manifest.csv")
    with open(manifest_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    keep, dropped = [], []
    for row in rows:
        problems = verify_row(set_dir, row, expected_make=expected_make)
        (keep if not problems else dropped).append((row, problems))

    for row, problems in dropped:
        for key, sub in (("filename_raw", "raw"), ("filename_jpeg", "jpeg")):
            p = os.path.join(set_dir, sub, row[key])
            if os.path.exists(p):
                os.remove(p)
        print(f"  제외: {row['filename_raw']} + {row['filename_jpeg']} - {problems}")

    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row, _ in keep:
            w.writerow({k: row[k] for k in COLUMNS})

    print(f"검증 완료: {len(keep)}개 유지, {len(dropped)}개 제외 (총 {len(rows)})")


def main():
    parser = argparse.ArgumentParser(description="로컬 사진 라이브러리에서 raw+jpeg 페어를 찾아 manifest에 추가")
    parser.add_argument("src_dir", help="raw+jpeg가 뒤섞여 있는 원본 폴더")
    parser.add_argument("set_dir", help="datasets/<브랜드>/contributed/<세트> 경로")
    parser.add_argument("--make", default="Hasselblad",
                         help="EXIF Make 검증에 쓸 기대 제조사명 (기본 Hasselblad)")
    args = parser.parse_args()
    src_dir = os.path.expanduser(args.src_dir)
    set_dir = os.path.expanduser(args.set_dir)

    already_raw = set(os.listdir(os.path.join(set_dir, "raw"))) \
        if os.path.isdir(os.path.join(set_dir, "raw")) else set()
    already_jpeg = set(os.listdir(os.path.join(set_dir, "jpeg"))) \
        if os.path.isdir(os.path.join(set_dir, "jpeg")) else set()

    pairs = find_pairs(src_dir, already_raw, already_jpeg)
    print(f"{len(pairs)}개 페어 매칭 (오프셋 0: {sum(1 for p in pairs if p[3] == 0)}개, "
          f"오프셋 보정: {sum(1 for p in pairs if p[3] != 0)}개)")

    append_manifest(set_dir, pairs, src_dir,
                     f"local (owner personal library, downloaded {date.today().isoformat()})")
    print("자동 검증(Lightroom/Photoshop 편집 오염 + 셔터 동기 재확인) 진행...")
    drop_failed(set_dir, expected_make=args.make)


if __name__ == "__main__":
    main()
