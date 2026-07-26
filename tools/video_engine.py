"""비디오 파일(mp4)에 population-fit 브랜드 룩을 프레임 단위로 적용하는
CLI. brands/*.py의 apply_*_look()은 이미 각 브랜드의 population 측정을
마쳤지만 정지 이미지 한 장만 다룬다 - 이 모듈은 새 색과학 측정 없이
그 결과를 비디오 프레임 시퀀스에 반복 적용하는 순수 엔지니어링이다.

지원 브랜드는 core.engine.apply_population_fit_look()을 공유하는 10개뿐
(canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony).
Fujifilm(프리셋마다 CLAHE 사용이 제각각)과 Hasselblad(별도 파이프라인,
자체 CLAHE)는 각자 다른 코드 경로라 이 모듈 하나로 묶을 수 없어 범위
밖이다 - 지원 대상 확장은 docs/superpowers/specs/2026-07-26-video-engine-design.md
참고.

비디오 모드는 사진 모드(apply_*_look())와 동일한 출력이 아니다 - CLAHE
(프레임별 적응형 로컬 대비 보정)를 생략한다. CLAHE를 프레임마다 그대로
쓰면 인접 프레임의 미세한 내용 차이만으로도 타일 히스토그램이 달라져
비디오에서 눈에 띄는 밝기/대비 깜빡임(flicker)이 생기기 때문이다
(core.engine.apply_population_fit_look_video_frame() 참고).

오디오 트랙은 보존하지 않는다 - 이 환경에 ffmpeg CLI/moviepy 등 오디오
mux 도구가 없다(cv2가 FFmpeg를 내장 빌드했지만 파이썬에서 오디오
스트림을 다루는 경로는 별도로 없음).

  python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
"""
import argparse
import inspect
import sys

import cv2

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
    오디오 트랙은 보존하지 않는다."""
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


def main():
    parser = argparse.ArgumentParser(
        description="비디오 파일에 population-fit 브랜드 룩 적용 (오디오 미보존)")
    parser.add_argument("input", help="입력 비디오 파일 경로")
    parser.add_argument("output", help="출력 비디오 파일 경로 (.mp4)")
    parser.add_argument("--brand", required=True, choices=sorted(SUPPORTED_BRANDS),
                         help="적용할 브랜드 룩")
    args = parser.parse_args()

    try:
        frame_count = process_video(args.input, args.output, args.brand)
    except (IOError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"완료: {frame_count}프레임 -> {args.output}")


if __name__ == "__main__":
    main()
