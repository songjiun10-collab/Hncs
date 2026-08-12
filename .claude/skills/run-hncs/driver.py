#!/usr/bin/env python3
"""Hncs 드라이버 - 이 프로젝트를 프로그램적으로 돌리고 눈으로 확인하는 하네스.

이 리포는 서버도 GUI도 아니라 "이미지 → 이미지" 라이브러리 + CLI 모음이다.
그래서 스크린샷에 해당하는 검증물은 **렌더된 출력 이미지**다. `sheet`가
24개 배포 룩을 한 장에 타일링해서 그걸 만든다 - 에이전트는 그 PNG를 열어
보면 파이프라인 전체가 살아있는지 한 번에 확인할 수 있다.

  python3 .claude/skills/run-hncs/driver.py env      # 뭐가 실행 가능한지
  python3 .claude/skills/run-hncs/driver.py smoke    # 외부 데이터 없이 되는 것 전부
  python3 .claude/skills/run-hncs/driver.py look hasselblad
  python3 .claude/skills/run-hncs/driver.py sheet

리포 루트에서 실행할 것(`core`/`brands`/`tools` 임포트 경로 때문).
"""
import argparse
import ast
import glob
import importlib
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

OUT_DIR = os.environ.get("HNCS_DRIVER_OUT", "/tmp/hncs_run")
# 커밋된 데모 합성본. 상단 60px에 "Original" 라벨이 구워져 있고 좌측 절반이
# 보정 전 원본이라, 라벨 아래 + 좌측 절반만 잘라 쓴다.
DEMO = os.path.join(ROOT, "docs/images/before_after_hncs.jpg")


def _cv2():
    import cv2
    return cv2


def default_source(cv2):
    """커밋된 데모에서 깨끗한 원본 사진 한 장을 잘라낸다."""
    im = cv2.imread(DEMO)
    if im is None:
        raise SystemExit(f"데모 이미지를 못 읽음: {DEMO}")
    return im[60:, :im.shape[1] // 2]


def shipped_looks():
    """brands/*.py의 사진용 apply_* 함수 목록 (video_frame 변형 제외).
    반환: [(모듈경로, 함수명), ...]

    **정정(2026-08)**: `def apply_*`만 잡고 population-fit 브랜드의
    `apply_canon_look = make_population_fit_look(...)` 같은 대입식은
    놓쳤었다(gui/tabs/brand_preview.py의 list_shipped_looks()에서 같은
    버그 발견 - 15개 브랜드 함수 누락) - 대입식도 같이 스캔하도록 수정."""
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "brands/*.py"))):
        mod = "brands." + os.path.basename(f)[:-3]
        if mod.endswith("__init__"):
            continue
        for n in ast.parse(open(f, encoding="utf-8").read()).body:
            if (isinstance(n, ast.FunctionDef) and n.name.startswith("apply_")
                    and "video_frame" not in n.name):
                out.append((mod, n.name))
            elif (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id.startswith("apply_")
                    and "video_frame" not in n.targets[0].id):
                out.append((mod, n.targets[0].id))
    return out


# ---------------------------------------------------------------- env

def cmd_env(args):
    """이 체크아웃에서 뭐가 실행 가능한지 보고. gitignore된 데이터에
    의존하는 경로가 많아서, 신선한 클론에서는 대부분 '없음'이 정상이다."""
    print("== 런타임 의존성 ==")
    for m in ["cv2", "numpy", "rawpy", "colour", "lensfunpy",
              "imageio_ffmpeg", "requests", "gdown", "OpenEXR"]:
        try:
            importlib.import_module(m)
            print(f"  OK    {m}")
        except Exception as e:
            print(f"  없음  {m}  ({type(e).__name__}) -> pip install -r requirements.txt")

    print("\n== 외부 바이너리 ==")
    for b, why in [("exiftool", "EXIF 판독(기여 데이터 검증/hybrid_engine)"),
                   ("darktable-cli", "evaluate_darktable_vs_rawpy 재현에만 필요")]:
        p = subprocess.run(["which", b], capture_output=True, text=True)
        print(f"  {'OK   ' if p.returncode == 0 else '없음 '} {b}  - {why}")

    print("\n== 데이터셋 (전부 .gitignore - 신선한 클론엔 없음) ==")
    checks = [
        ("raw_calib_cache/", "핫셀블라드 raw+jpeg 13쌍 - calibrate / evaluate_* / hybrid_engine.main"),
        ("downloaded_samples/", "population 샘플 - tools.analyze (없으면 네트워크에서 받음)"),
        ("raw_calib_cache_fuji/", "후지 raw+jpeg 3쌍 - evaluate_fuji_demosaic"),
    ]
    for path, why in checks:
        full = os.path.join(ROOT, path)
        n = len(os.listdir(full)) if os.path.isdir(full) else 0
        print(f"  {'OK   ' if n else '없음 '} {path:24s} {n:>4}개  - {why}")

    print(f"\n== 배포 룩 {len(shipped_looks())}개 (데이터 불필요, 항상 실행 가능) ==")


# ---------------------------------------------------------------- look

def cmd_look(args):
    """브랜드 룩 하나를 실제 사진에 적용해서 파일로 떨군다."""
    cv2 = _cv2()
    os.makedirs(OUT_DIR, exist_ok=True)
    src = cv2.imread(args.src) if args.src else default_source(cv2)
    if src is None:
        raise SystemExit(f"입력 이미지를 못 읽음: {args.src}")

    target = None
    for mod, fn in shipped_looks():
        if fn == args.look or fn == f"apply_{args.look}" or mod.endswith(f".{args.look}"):
            target = (mod, fn)
            break
    if target is None:
        print("사용 가능한 룩:")
        for mod, fn in shipped_looks():
            print(f"  {fn:32s} ({mod})")
        raise SystemExit(f"'{args.look}' 을 못 찾음")

    mod, fn = target
    func = getattr(importlib.import_module(mod), fn)
    out = func(src)
    dst = args.out or os.path.join(OUT_DIR, f"look_{fn}.png")
    cv2.imwrite(dst, out)
    print(f"{fn}({src.shape}) -> {dst}")
    print(f"  평균 밝기 {src.mean():.1f} -> {out.mean():.1f}")
    return 0


# ---------------------------------------------------------------- sheet

def cmd_sheet(args):
    """배포 룩 전부를 한 사진에 적용해 컨택트 시트 PNG로 타일링.
    이 프로젝트의 '스크린샷' - 이 한 장을 열어보면 전 파이프라인이
    살아있는지 한눈에 보인다."""
    cv2 = _cv2()
    import numpy as np
    os.makedirs(OUT_DIR, exist_ok=True)
    src = cv2.imread(args.src) if args.src else default_source(cv2)
    if src is None:
        raise SystemExit(f"입력 이미지를 못 읽음: {args.src}")

    thumb_w = 320
    scale = thumb_w / src.shape[1]
    small = cv2.resize(src, (thumb_w, int(src.shape[0] * scale)),
                        interpolation=cv2.INTER_AREA)

    tiles = [("(원본)", small)]
    failed = []
    for mod, fn in shipped_looks():
        try:
            func = getattr(importlib.import_module(mod), fn)
            out = func(small.copy())
            # 흑백 프리셋(apply_acros/apply_monochrome)은 의도적으로 2D
            # 단일채널을 반환한다 - tests/test_brands.py의
            # test_mono_presets_return_single_channel이 그 계약을 검증한다.
            # 타일링하려면 3채널로 되돌려야 한다.
            if out.ndim == 2:
                out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
            tiles.append((fn.replace("apply_", ""), out))
        except Exception as e:
            failed.append(f"{fn}: {type(e).__name__}: {e}")
            print(f"  FAIL {fn}: {type(e).__name__}: {e}")

    cols = args.cols
    rows = (len(tiles) + cols - 1) // cols
    th, tw = small.shape[:2]
    pad, label_h = 6, 22
    sheet = np.full(((th + label_h + pad) * rows + pad, (tw + pad) * cols + pad, 3),
                     32, dtype=np.uint8)
    for i, (name, img) in enumerate(tiles):
        r, c = divmod(i, cols)
        y = pad + r * (th + label_h + pad)
        x = pad + c * (tw + pad)
        sheet[y + label_h:y + label_h + th, x:x + tw] = img
        cv2.putText(sheet, name[:28], (x + 2, y + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (235, 235, 235), 1, cv2.LINE_AA)

    dst = args.out or os.path.join(OUT_DIR, "contact_sheet.png")
    cv2.imwrite(dst, sheet)
    print(f"\n컨택트 시트: {dst}  ({len(tiles)}칸 = 원본 1 + 룩 {len(tiles)-1})")
    if failed:
        print(f"실패 {len(failed)}건:")
        for f in failed:
            print("  ", f)
        return 1
    print("이 PNG를 열어서 각 칸이 서로 다르게 렌더됐는지 눈으로 확인할 것.")
    return 0


# ---------------------------------------------------------------- smoke

def cmd_smoke(args):
    """외부 데이터 없이 동작해야 하는 경로 전부를 실행하고 pass/fail 집계."""
    cv2 = _cv2()
    os.makedirs(OUT_DIR, exist_ok=True)
    src_path = os.path.join(OUT_DIR, "_smoke_src.jpg")
    cv2.imwrite(src_path, default_source(cv2))

    steps = [
        ("라이브러리: apply_hncs 직접 호출", None),
        ("CLI: tools.export_lut --list",
         [sys.executable, "-m", "tools.export_lut", "--list"]),
        ("CLI: tools.export_lut (17격자 .cube 생성)",
         [sys.executable, "-m", "tools.export_lut", "hasselblad",
          os.path.join(OUT_DIR, "smoke.cube"), "--size", "17"]),
        ("CLI: tools.classify_brand predict",
         [sys.executable, "-m", "tools.classify_brand", "predict", src_path]),
        ("CLI: tools.denoise",
         [sys.executable, "-m", "tools.denoise", src_path,
          os.path.join(OUT_DIR, "smoke_denoise.jpg"), "--strength", "3"]),
        # EXIF 없는 입력이라 --source 필수. 빼면 "브랜드를 못 알아봄"으로 종료 1.
        ("CLI: hybrid_engine.convert (--source 필수)",
         [sys.executable, "-m", "hybrid_engine.convert", src_path,
          os.path.join(OUT_DIR, "smoke_convert.jpg"),
          "--source", "nikon", "--target", "hasselblad"]),
    ]

    env = dict(os.environ, PYTHONWARNINGS="ignore")
    ok = fail = 0
    for name, cmd in steps:
        if cmd is None:
            try:
                from brands.hasselblad import apply_hncs
                out = apply_hncs(default_source(cv2))
                assert out.shape == default_source(cv2).shape and out.dtype.name == "uint8"
                print(f"  PASS  {name}")
                ok += 1
            except Exception as e:
                print(f"  FAIL  {name}: {type(e).__name__}: {e}")
                fail += 1
            continue
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                            timeout=600, env=env)
        if p.returncode == 0:
            print(f"  PASS  {name}")
            ok += 1
        else:
            print(f"  FAIL  {name}  (exit {p.returncode})")
            print("        " + (p.stderr.strip().split("\n")[-1] if p.stderr.strip()
                                 else p.stdout.strip().split("\n")[-1]))
            fail += 1

    print(f"\n{ok} pass / {fail} fail")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("env", help="의존성/데이터 가용성 보고")

    p = sub.add_parser("smoke", help="외부 데이터 없이 되는 경로 전부 실행")

    p = sub.add_parser("look", help="브랜드 룩 하나를 사진에 적용")
    p.add_argument("look", help="예: hasselblad, apply_canon_look, astia")
    p.add_argument("--src", help="입력 이미지(기본: 커밋된 데모에서 crop)")
    p.add_argument("--out", help="출력 경로")

    p = sub.add_parser("sheet", help="배포 룩 전부 타일링한 컨택트 시트")
    p.add_argument("--src")
    p.add_argument("--out")
    p.add_argument("--cols", type=int, default=5)

    args = ap.parse_args()
    return {"env": cmd_env, "smoke": cmd_smoke,
            "look": cmd_look, "sheet": cmd_sheet}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
