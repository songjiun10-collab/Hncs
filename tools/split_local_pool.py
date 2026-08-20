"""여러 브랜드 raw+jpeg가 뒤섞인 로컬 폴더(~/local-work 같은)를 EXIF Make
기준으로 브랜드별 `datasets/<브랜드>/contributed/<세트>/`로 나눠 담는 CLI.
매칭은 `tools.build_local_manifest`의 `find_pairs()`(전역 최적 1:1 배정)를
그대로 재사용하되, 브랜드별로 나눠 호출하는 대신 **전체 풀을 한 번에
매칭한 뒤** raw의 EXIF Make로 그룹핑해서 각 브랜드 세트에 move한다 -
브랜드별로 반복 호출하면 매번 전체 jpeg 풀을 다시 스캔+비교해야 하고,
Make 불일치로 걸러지는 오탐 매칭(다른 브랜드 raw가 우연히 시간이 맞는
enemy jpeg를 선점)도 늘어난다.

  python3 -m tools.split_local_pool ~/local-work

Make 매핑에 없는 raw(알려지지 않은 브랜드)는 매칭 자체에서 제외되지
않고 남아있지만 어느 세트로도 옮기지 않는다 - 리포트에서 "미분류"로
표시.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.build_local_manifest import append_manifest, drop_failed, find_pairs

_MAKE_TO_BRAND = {
    "hasselblad": ("hasselblad", "hasselblad"),
    "canon": ("canon", "canon"),
    "sony": ("sony", "sony"),
    "fujifilm": ("fuji", "fujifilm"),
    "nikon corporation": ("nikon", "nikon"),
    "leica camera ag": ("leica", "leica"),
    "sigma": ("sigma", "sigma"),
}


def _brand_for_make(make):
    return _MAKE_TO_BRAND.get((make or "").strip().lower())


def main():
    ap = argparse.ArgumentParser(description="여러 브랜드가 섞인 로컬 폴더를 브랜드별 contributed 세트로 분리")
    ap.add_argument("src_dir", help="raw+jpeg가 뒤섞여 있는 원본 폴더")
    ap.add_argument("--set-name", default="local-work-2026-08",
                     help="브랜드별 datasets/<브랜드>/contributed/<세트> 세트 이름")
    args = ap.parse_args()
    src_dir = os.path.expanduser(args.src_dir)

    pairs = find_pairs(src_dir, already_raw=set(), already_jpeg=set())
    print(f"전체 {len(pairs)}개 페어 매칭 완료. 브랜드별로 분류합니다...")

    by_brand = {}
    unclassified = []
    for r, j, delta, oh, ambiguous in pairs:
        mapped = _brand_for_make(r.get("make"))
        if mapped is None:
            unclassified.append(r["filename"])
            continue
        brand_dir, expected_make = mapped
        by_brand.setdefault(brand_dir, (expected_make, []))[1].append((r, j, delta, oh, ambiguous))

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for brand_dir, (expected_make, brand_pairs) in sorted(by_brand.items()):
        set_dir = os.path.join(root, "datasets", brand_dir, "contributed", args.set_name)
        print(f"\n== {brand_dir} ({len(brand_pairs)}개 페어) -> {set_dir} ==")
        append_manifest(set_dir, brand_pairs, src_dir,
                         f"local (owner personal library, split {args.set_name})")
        drop_failed(set_dir, expected_make=expected_make)

    if unclassified:
        print(f"\n미분류 raw {len(unclassified)}개 (알려지지 않은 Make, 이동 안 함): "
              f"{unclassified[:10]}{'...' if len(unclassified) > 10 else ''}")


if __name__ == "__main__":
    main()
