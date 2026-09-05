"""후지 `local-work-2026-08` 세트에서 **같은 장면을 필름시뮬레이션만 바꿔
촬영한 묶음**을 찾는다.

**왜**: 이 세트의 나머지 페어는 장면이 전부 달라서, `apply_classic_negative`
같은 필름모드 함수의 오차에 "장면 차이"와 "필름모드 변환 차이"가 섞여
들어간다. 같은 장면을 모드만 바꿔 찍은 묶음이 있으면 장면이 상수로 고정되어
**필름모드 변환 자체만** 분리해서 볼 수 있다 - 이 세트에서 가장 값어치 있는
부분집합이다. 사용자가 직접 알려준 리드(2026-09-04: "후지에 같은장면 필터만
바꿔서 찍은거 있음").

**시간으로 못 묶는다(확인함)**: 사용자가 5~6초 간격이라고 했고 실제 EXIF
간격도 그 수준인데, 이 세트의 GFX50S II는 **카메라 시계가 미설정**이라
`DateTimeOriginal`이 전부 `2021:01:01 00:00~00:01`이다 - 104장이 80초 안에
들어가서 시간 간격으로는 장면 경계가 전혀 안 갈린다(이 스크립트의 초판이
그렇게 묶었다가 104장짜리 가짜 묶음이 나와서 폐기). 그래서 **이미지 내용**
으로 묶는다 - "같은 장면"의 정의 자체이기도 하고, 깨진 시계에 의존하지
않는다.

**방법**: 각 JPEG을 `THUMB`x`THUMB` 그레이스케일로 줄이고 프레임별로
표준화(평균 0/표준편차 1)한다 - 필름모드가 다르면 밝기/대비/색이 통째로
달라지므로, 표준화하지 않으면 같은 장면인데도 멀어진다. 표준화한 썸네일
사이의 평균 절대차가 `MAX_DIST` 이하면 같은 장면으로 보고 union-find로
묶은 뒤, 묶음 안에 서로 다른 필름모드가 2개 이상이면 보고한다.

**한계**: 내용 기반 매칭이라 구도가 거의 같은 다른 장면(연사 등)도 한
묶음에 들어올 수 있다. 리포트에 묶음별 최대 거리를 같이 실으니 임계값을
바꿔가며 확인할 것.

**세트 인자**: 기본은 `local-work-2026-08`이고, 두 번째 인자로 다른
`datasets/fuji/contributed/<세트>`를 지정할 수 있다 - 묶음 표본이 1개라
`tools/evaluate_fuji_film_mode_separation.py`가 부트스트랩 CI를 못 냈기
때문에(2026-09-04) 다른 세트에서 묶음을 더 찾으려고 일반화했다.

  python3 -m tools.find_fuji_same_scene_film_mode_groups [max_dist] [세트명]
"""
import csv
import json
import os
import subprocess
import sys

import cv2
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRIB = os.path.join(BASE, "datasets", "fuji", "contributed")
DEFAULT_SET = "local-work-2026-08"

THUMB = 32
MAX_DIST = 0.35  # 표준화 썸네일 평균 절대차


def read_exif(jpeg_dir):
    out = subprocess.run(
        ["exiftool", "-q", "-s3", "-T", "-FileName", "-Model",
         "-DateTimeOriginal", "-FilmMode", jpeg_dir],
        capture_output=True, text=True, timeout=600).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        name, model, dt, mode = (p.strip() for p in parts)
        rows.append(dict(jpeg=name, camera=model, time=dt,
                         film_mode=mode if mode != "-" else None))
    return rows


def thumbnail(path):
    """표준화 그레이스케일 썸네일 - 필름모드에 따른 밝기/대비 차이를 빼고
    구도만 남긴다."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    t = cv2.resize(img, (THUMB, THUMB), interpolation=cv2.INTER_AREA).astype(np.float64)
    return (t - t.mean()) / (t.std() + 1e-6)


class _Union:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main():
    max_dist = float(sys.argv[1]) if len(sys.argv) > 1 else MAX_DIST
    set_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SET
    set_dir = os.path.join(CONTRIB, set_name)
    out_report = os.path.join(set_dir, "same_scene_film_mode_groups.json")
    print(f"세트 {set_name}")

    rows = read_exif(os.path.join(set_dir, "jpeg"))
    print(f"EXIF 읽은 JPEG {len(rows)}장")

    raw_by_jpeg = {}
    with open(os.path.join(set_dir, "manifest.csv"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw_by_jpeg[row["filename_jpeg"]] = row["filename_raw"]

    keep, thumbs = [], []
    for r in rows:
        t = thumbnail(os.path.join(set_dir, "jpeg", r["jpeg"]))
        if t is not None:
            keep.append(r)
            thumbs.append(t)
    T = np.stack(thumbs)
    n = len(keep)
    print(f"썸네일 {n}장, 임계값 {max_dist}")

    uf = _Union(n)
    dist = np.zeros((n, n))
    for i in range(n):
        d = np.mean(np.abs(T[i][None, ...] - T), axis=(1, 2))
        dist[i] = d
        for j in np.where(d <= max_dist)[0]:
            if j > i and keep[i]["camera"] == keep[j]["camera"]:
                uf.union(i, j)

    clusters = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    multi = []
    for idx in clusters.values():
        modes = {keep[i]["film_mode"] for i in idx if keep[i]["film_mode"]}
        if len(modes) >= 2:
            multi.append(idx)

    print(f"장면 묶음 {len(clusters)}개 중 필름모드 2종 이상: {len(multi)}개\n")
    report_groups = []
    for gi, idx in enumerate(sorted(multi, key=lambda x: -len(x)), 1):
        sub = dist[np.ix_(idx, idx)]
        modes = sorted({keep[i]["film_mode"] for i in idx if keep[i]["film_mode"]})
        print(f"[{gi}] {keep[idx[0]]['camera']}  {len(idx)}장  "
              f"모드 {len(modes)}종  묶음내 최대거리 {sub.max():.3f}")
        for i in idx:
            print(f"       {keep[i]['jpeg']}  {keep[i]['film_mode']}  "
                  f"raw={raw_by_jpeg.get(keep[i]['jpeg'], '(없음)')}")
        report_groups.append(dict(
            camera=keep[idx[0]]["camera"], n_frames=len(idx),
            film_modes=modes, max_intra_distance=float(sub.max()),
            frames=[dict(jpeg=keep[i]["jpeg"], raw=raw_by_jpeg.get(keep[i]["jpeg"]),
                         time=keep[i]["time"], film_mode=keep[i]["film_mode"])
                    for i in idx]))

    report = {
        "purpose": "같은 장면을 필름시뮬레이션만 바꿔 촬영한 묶음 - 필름모드 "
                   "변환 자체만 분리해서 평가할 수 있는 부분집합",
        "lead": "사용자 제보(2026-09-04): 후지에 같은 장면 필터만 바꿔 찍은 것 있음",
        "set": f"datasets/fuji/contributed/{set_name}",
        "grouping": f"표준화 {THUMB}x{THUMB} 그레이스케일 썸네일 평균 절대차 "
                    f"<= {max_dist}, 같은 바디끼리만, union-find",
        "why_not_time": "local-work-2026-08의 GFX50S II는 카메라 시계 미설정으로 "
                        "DateTimeOriginal이 전부 2021:01:01 00:00~00:01 - "
                        "104장이 80초 안에 들어가 시간으로는 장면이 안 갈린다",
        "n_jpeg": n,
        "n_scene_clusters": len(clusters),
        "n_multi_mode_clusters": len(multi),
        "groups": report_groups,
    }
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n리포트: {out_report}")


if __name__ == "__main__":
    main()
