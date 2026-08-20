"""비디오 파일(mp4)에 population-fit 브랜드 룩을 프레임 단위로 적용하는
CLI. brands/*.py의 apply_*_look()은 이미 각 브랜드의 population 측정을
마쳤지만 정지 이미지 한 장만 다룬다 - 이 모듈은 새 색과학 측정 없이
그 결과를 비디오 프레임 시퀀스에 반복 적용하는 순수 엔지니어링이다.

지원 브랜드는 22개: population-fit 10개(canon/leica/nikon/olympus/
panasonic/pentax/phaseone/ricoh_gr/sigma/sony, core.engine.
apply_population_fit_look()을 공유, process_video()/
process_video_with_audio()가 처리) + Fuji/Hasselblad 12개(fuji_astia/
fuji_pro_neg_std/fuji_pro_neg_hi/fuji_eterna_cinema/
fuji_eterna_bleach_bypass/fuji_nostalgic_neg/fuji_reala_ace/
fuji_classic_negative/fuji_acros/fuji_monochrome/fuji_classic_chrome/
hasselblad, process_video_v2()/process_video_v2_with_audio()가 처리 -
Fuji 프리셋 중 CLAHE를 쓰는 건 apply_pro_neg_hi/apply_nostalgic_neg_v3/
apply_classic_chrome_v2 셋이라 그 셋과 Hasselblad apply_hncs만 CLAHE
생략 변형을 추가했고 나머지는 수정 없이 재사용한다. 자세한 조사 내용은
docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md
참고). Hasselblad는 apply_hncs(Stable)만 지원 - day/night/learned
프리셋은 범위 밖. fuji_nostalgic_neg/fuji_classic_chrome은 각각
apply_nostalgic_neg_v3/apply_classic_chrome_v2의 CLAHE 생략판을 쓴다
(2026-08, 페어 매칭 버그 수정 후 재도출된 정정판으로 교체 - brands/
fuji.py의 apply_nostalgic_neg(v1)/apply_classic_chrome(v1)은 정본
그대로 남아있지만 이 레지스트리는 최신 정정판을 가리킨다).

비디오 모드는 사진 모드(apply_*_look())와 동일한 출력이 아니다 - CLAHE
(프레임별 적응형 로컬 대비 보정)를 생략한다. CLAHE를 프레임마다 그대로
쓰면 인접 프레임의 미세한 내용 차이만으로도 타일 히스토그램이 달라져
비디오에서 눈에 띄는 밝기/대비 깜빡임(flicker)이 생기기 때문이다
(core.engine.apply_population_fit_look_video_frame() 참고).

오디오 트랙은 기본으로 보존된다 - process_video_with_audio()가
imageio-ffmpeg(정적 ffmpeg 바이너리를 pip로 받아옴)로 색보정된 무음
비디오에 원본의 첫 번째 오디오 트랙을 무손실 remux한다(입력에 오디오가
없으면 출력도 무음, 에러 아님). 재인코딩·다중 트랙 선택은 하지 않는다.
프레임 색보정 자체는 process_video()가 그대로 담당한다(오디오와 무관).

  python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
"""
import argparse
import inspect
import os
import shutil
import subprocess
import sys
import tempfile

import cv2
import imageio_ffmpeg

from brands.canon import apply_canon_look
from brands.leica import apply_leica_look
from brands.nikon import apply_nikon_look
from brands.olympus import apply_olympus_look
from brands.panasonic import apply_panasonic_look
from brands.pentax import apply_pentax_look
from brands.phaseone import apply_phaseone_look
from brands.ricoh_gr import apply_ricoh_gr_look
from brands.sigma import apply_sigma_look
from brands.sony import apply_sony_look
from brands.fuji import (
    apply_astia, apply_pro_neg_std, apply_pro_neg_hi_video_frame,
    apply_eterna_cinema, apply_eterna_bleach_bypass,
    apply_nostalgic_neg_v3_video_frame,
    apply_reala_ace, apply_classic_negative, apply_acros, apply_monochrome,
    apply_classic_chrome_v2_video_frame,
)
from brands.hasselblad import apply_hncs_video_frame
from core.engine import apply_population_fit_look_video_frame

_BRAND_FUNCTIONS = {
    "canon": apply_canon_look,
    "leica": apply_leica_look,
    "nikon": apply_nikon_look,
    "olympus": apply_olympus_look,
    "panasonic": apply_panasonic_look,
    "pentax": apply_pentax_look,
    "phaseone": apply_phaseone_look,
    "ricoh_gr": apply_ricoh_gr_look,
    "sigma": apply_sigma_look,
    "sony": apply_sony_look,
}

SUPPORTED_BRANDS = frozenset(_BRAND_FUNCTIONS)


def _grayscale_to_bgr_frame(frame_func):
    """apply_acros/apply_monochrome처럼 1채널 그레이스케일을 반환하는
    함수를 3채널 BGR 프레임을 반환하도록 감싼다(cv2.VideoWriter가 컬러
    프레임을 가정하므로)."""
    def wrapped(img_bgr):
        gray = frame_func(img_bgr)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return wrapped


_EXPANDED_BRAND_FUNCTIONS = {
    "fuji_astia": apply_astia,
    "fuji_pro_neg_std": apply_pro_neg_std,
    "fuji_pro_neg_hi": apply_pro_neg_hi_video_frame,
    "fuji_eterna_cinema": apply_eterna_cinema,
    "fuji_eterna_bleach_bypass": apply_eterna_bleach_bypass,
    "fuji_nostalgic_neg": apply_nostalgic_neg_v3_video_frame,
    "fuji_reala_ace": apply_reala_ace,
    "fuji_classic_negative": apply_classic_negative,
    "fuji_acros": _grayscale_to_bgr_frame(apply_acros),
    "fuji_monochrome": _grayscale_to_bgr_frame(apply_monochrome),
    "fuji_classic_chrome": apply_classic_chrome_v2_video_frame,
    "hasselblad": apply_hncs_video_frame,
}

EXPANDED_SUPPORTED_BRANDS = frozenset(_EXPANDED_BRAND_FUNCTIONS)


def brand_video_params(brand_name):
    """brand_name -> (toe_lift, shoulder_start, white_point). 각
    apply_*_look()의 공개 기본 인자값을 inspect로 읽어온다 - brands/*.py의
    비공개 _TOE_LIFT류 상수를 직접 import하지 않는다."""
    if brand_name not in _BRAND_FUNCTIONS:
        raise ValueError(
            f"지원하지 않는 브랜드: {brand_name!r} "
            f"(지원: {', '.join(sorted(SUPPORTED_BRANDS))})"
        )
    sig = inspect.signature(_BRAND_FUNCTIONS[brand_name])
    return (
        sig.parameters["toe_lift"].default,
        sig.parameters["shoulder_start"].default,
        sig.parameters["white_point"].default,
    )


def process_video(input_path, output_path, brand_name, progress_every=100):
    """input_path의 비디오를 읽어 brand_name 룩(CLAHE 생략, 톤 LUT만)을
    프레임마다 적용해 output_path에 쓴다. 처리한 프레임 수를 반환한다.
    오디오 트랙은 보존하지 않는다(오디오는 process_video_with_audio()가
    별도로 처리)."""
    toe_lift, shoulder_start, white_point = brand_video_params(brand_name)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise IOError(f"입력 비디오를 열 수 없음: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise IOError(f"출력 비디오를 열 수 없음: {output_path}")

    frame_count = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            out_frame = apply_population_fit_look_video_frame(
                frame, toe_lift, shoulder_start, white_point)
            writer.write(out_frame)
            frame_count += 1
            if frame_count % progress_every == 0:
                print(f"{frame_count}프레임 처리됨...", file=sys.stderr)
    finally:
        cap.release()
        writer.release()

    return frame_count


def mux_audio(video_only_path, audio_source_path, final_output_path):
    """video_only_path(오디오 없는 색보정 비디오)에 audio_source_path의
    첫 번째 오디오 트랙을 무손실로 입혀 final_output_path에 쓴다.
    audio_source_path에 오디오가 없으면 final_output_path도 무음(에러
    아님) - ffmpeg의 optional map(`?`)이 처리한다. 재인코딩 없음
    (-c:v copy -c:a copy)."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_exe, "-y",
         "-i", video_only_path, "-i", audio_source_path,
         "-map", "0:v:0", "-map", "1:a:0?",
         "-c:v", "copy", "-c:a", "copy",
         final_output_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if os.path.exists(final_output_path):
            os.remove(final_output_path)
        raise IOError(f"오디오 remux 실패 (ffmpeg exit {result.returncode}): "
                       f"{result.stderr[-500:]}")


def process_video_with_audio(input_path, output_path, brand_name, progress_every=100):
    """process_video()로 색보정한 뒤 input_path의 오디오를 다시 입혀서
    output_path에 쓴다 - CLI의 기본 진입점. process_video() 자체는
    수정하지 않는다."""
    if not output_path.lower().endswith(".mp4"):
        raise ValueError(
            f"출력 파일은 .mp4만 지원함: {output_path!r}"
        )
    tmp_dir = tempfile.mkdtemp()
    tmp_video_only = os.path.join(tmp_dir, "video_only.mp4")
    try:
        frame_count = process_video(input_path, tmp_video_only, brand_name, progress_every)
        mux_audio(tmp_video_only, input_path, output_path)
        return frame_count
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def process_video_v2(input_path, output_path, brand_name, progress_every=100):
    """확장 브랜드(Fuji 9개 무수정 + apply_pro_neg_hi/apply_hncs CLAHE
    생략 변형) 전용 - process_video()와 거의 동일한 I/O 구조지만, 프레임
    처리 함수가 (toe_lift, shoulder_start, white_point) 3개 인자 대신
    단일 인자 콜백이라는 점이 다르다. process_video()는 수정하지 않는다
    (나란히 추가)."""
    if brand_name not in _EXPANDED_BRAND_FUNCTIONS:
        raise ValueError(
            f"지원하지 않는 확장 브랜드: {brand_name!r} "
            f"(지원: {', '.join(sorted(EXPANDED_SUPPORTED_BRANDS))})"
        )
    frame_func = _EXPANDED_BRAND_FUNCTIONS[brand_name]

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise IOError(f"입력 비디오를 열 수 없음: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise IOError(f"출력 비디오를 열 수 없음: {output_path}")

    frame_count = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            out_frame = frame_func(frame)
            writer.write(out_frame)
            frame_count += 1
            if frame_count % progress_every == 0:
                print(f"{frame_count}프레임 처리됨...", file=sys.stderr)
    finally:
        cap.release()
        writer.release()

    return frame_count


def process_video_v2_with_audio(input_path, output_path, brand_name, progress_every=100):
    """process_video_v2()로 색보정한 뒤 mux_audio()로 원본 오디오를
    입힌다 - process_video_with_audio()와 같은 구조지만 process_video_v2()를
    쓴다는 점만 다르다. process_video_with_audio()는 수정하지 않는다."""
    if not output_path.lower().endswith(".mp4"):
        raise ValueError(
            f"출력 파일은 .mp4만 지원함: {output_path!r}"
        )
    tmp_dir = tempfile.mkdtemp()
    tmp_video_only = os.path.join(tmp_dir, "video_only.mp4")
    try:
        frame_count = process_video_v2(input_path, tmp_video_only, brand_name, progress_every)
        mux_audio(tmp_video_only, input_path, output_path)
        return frame_count
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="비디오 파일에 브랜드 룩 적용 (오디오 트랙 기본 보존)")
    parser.add_argument("input", help="입력 비디오 파일 경로")
    parser.add_argument("output", help="출력 비디오 파일 경로 (.mp4)")
    all_brands = sorted(SUPPORTED_BRANDS | EXPANDED_SUPPORTED_BRANDS)
    parser.add_argument("--brand", required=True, choices=all_brands,
                         help="적용할 브랜드 룩")
    args = parser.parse_args()

    try:
        if args.brand in SUPPORTED_BRANDS:
            frame_count = process_video_with_audio(args.input, args.output, args.brand)
        else:
            frame_count = process_video_v2_with_audio(args.input, args.output, args.brand)
    except (IOError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"완료: {frame_count}프레임 -> {args.output}")


if __name__ == "__main__":
    main()
