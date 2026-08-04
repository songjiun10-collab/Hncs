"""SD카드 삭제/포맷 사진 복구 CLI.

    python3 -m tools.recover_sdcard <이미지파일> <출력폴더> [--mode {undelete,carve,both}]

**반드시 이미지 파일(.img)에 대해서만 동작한다** - 라이브 블록 디바이스를
직접 읽지 않는다(안전을 위한 설계 선택, 실수로 쓰기 명령이 섞여 들어갈
위험을 원천 차단). SD카드 자체를 먼저 읽기전용으로 이미지 떠야 한다:

    macOS: diskutil list 로 식별 번호 확인 후
           sudo dd if=/dev/rdiskN of=card.img bs=4m
           (rdiskN이 diskN보다 훨씬 빠름 - raw/char 디바이스)
           카드에는 절대 안 쓰므로 of=/dev/rdiskN으로 두면 안 된다.

1단계(undelete, `core/sdcard_undelete.py`): FAT32/exFAT 디렉토리와
클러스터 체인이 아직 살아있으면 파일명/크기 그대로 복구 - 카빙보다
훨씬 정확하니 먼저 시도한다. 2단계(carve, `core/sdcard_carve.py`):
포맷됐거나 파일시스템이 손상돼 1단계가 실패한 파일을 위해 시그니처로
훑어 잘라낸다. 둘 다 돌리면 같은 파일이 undeleted/와 carved/ 양쪽에
중복으로 나올 수 있다(의도된 동작 - 두 방법이 서로 다른 이름/정확도로
같은 실제 파일을 찾아낸 것일 뿐, 확인 후 하나를 고르면 된다).
"""
import argparse
import os
import stat
import sys

from core.sdcard_undelete import detect_filesystem, recover_fat32, recover_exfat
from core.sdcard_carve import carve


def _reject_if_device(path):
    st = os.stat(path)
    if stat.S_ISBLK(st.st_mode) or stat.S_ISCHR(st.st_mode):
        print(f"오류: {path}는 블록/캐릭터 디바이스입니다 - 이 도구는 "
              f"안전을 위해 dd 등으로 미리 뜬 이미지 파일만 다룹니다.",
              file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image_path", help="dd 등으로 미리 뜬 SD카드 이미지 파일(.img)")
    parser.add_argument("out_dir", help="복구 결과를 쓸 폴더")
    parser.add_argument("--mode", choices=["undelete", "carve", "both"], default="both")
    args = parser.parse_args()

    _reject_if_device(args.image_path)
    os.makedirs(args.out_dir, exist_ok=True)

    if args.mode in ("undelete", "both"):
        fs = detect_filesystem(args.image_path)
        print(f"파일시스템: {fs}")
        if fs in ("fat32", "exfat"):
            out_sub = os.path.join(args.out_dir, "undeleted")
            recover_fn = recover_fat32 if fs == "fat32" else recover_exfat
            results = recover_fn(args.image_path, out_sub)
            ok = [r for r in results if r["recovered"]]
            failed = [r for r in results if not r["recovered"]]
            print(f"[undelete] 복구 {len(ok)}개 / 실패(카빙 필요) {len(failed)}개 "
                  f"-> {out_sub}")
            for r in ok:
                print(f"  OK   {r['path']:40s} {r['size']:>10d}B  ({r['method']})")
            for r in failed:
                print(f"  FAIL {r['path']:40s} {r['size']:>10d}B  (체인 복구 불가)")
        else:
            print("[undelete] FAT32/exFAT이 아니라 건너뜁니다 - carve만 시도합니다.")

    if args.mode in ("carve", "both"):
        out_sub = os.path.join(args.out_dir, "carved")
        results = carve(args.image_path, out_sub)
        n_approx = sum(1 for r in results if r["approx"])
        print(f"[carve] {len(results)}개 발견 (근사치 {n_approx}개) -> {out_sub}")
        by_kind = {}
        for r in results:
            by_kind.setdefault(r["kind"], []).append(r)
        for kind, items in sorted(by_kind.items()):
            print(f"  {kind}: {len(items)}개")
        if n_approx:
            print("  주의: 근사치로 표시된 파일은 다음 파일 시작 위치에서 잘랐거나"
                  "(X3F는 항상 근사치) 잘렸을 수 있습니다 - 열어서 확인하세요.")


if __name__ == "__main__":
    main()
