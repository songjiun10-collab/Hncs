"""
RAW 디코딩 및 TIFF 입출력. rawpy로 어떤 카메라의 RAW든 16비트 Linear RGB로
순수하게 뽑아내고(감마/톤커브 없음 - 이후 파이프라인이 전부 처리), 최종
결과를 16비트 무손실 TIFF로 저장한다.
"""
import os
import subprocess
import tempfile

import numpy as np
import rawpy
import cv2
import colour


def decode_raw(raw_path, demosaic_algorithm=None, chromatic_aberration=None):
    """RAW -> Linear RGB, float64 [0, 1] 근방(하이라이트는 1을 넘을 수
    있음), shape (H, W, 3), RGB 순서. 카메라 고유 색공간이 아니라 sRGB
    프라이머리 기준 선형광(linear light) 값 - 이후 core/pipeline이
    이 프라이머리를 그대로 XYZ 변환 기준으로 쓴다.

    demosaic_algorithm: None(기본값)이면 rawpy 기본 데모자이크를 쓰고
    기존 호출부와 100% 동일하게 동작한다. rawpy.DemosaicAlgorithm 값을
    넘기면 raw.postprocess()에 그대로 전달된다(예: X-Trans용 DHT 비교
    실험 - tools/evaluate_fuji_demosaic.py 참고). AMAZE는 이 프로젝트가
    쓰는 LibRaw 빌드에 GPL3 데모자이크 팩이 없어 런타임 에러가 난다.

    chromatic_aberration: None(기본값)이면 색수차 보정 없이 기존과
    100% 동일하게 동작한다(rawpy 기본값 (1.0, 1.0)과 결과가 바이트
    단위로 동일함을 실측 확인). (red_scale, blue_scale) 튜플을 넘기면
    raw.postprocess()에 그대로 전달돼 R/B 채널을 스케일링해서 렌즈
    색수차를 보정한다(tools/evaluate_chromatic_aberration.py 참고)."""
    kwargs = dict(
        use_camera_wb=True,
        no_auto_bright=True,
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        gamma=(1, 1),  # 순수 linear
    )
    if demosaic_algorithm is not None:
        kwargs["demosaic_algorithm"] = demosaic_algorithm
    if chromatic_aberration is not None:
        kwargs["chromatic_aberration"] = chromatic_aberration
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(**kwargs)
    return rgb16.astype(np.float64) / 65535.0


def decode_raw_native(raw_path):
    """RAW -> 카메라 네이티브 linear RGB, float64 [0, 1] 근방,
    shape (H, W, 3), RGB 순서.

    decode_raw()와 결정적으로 다른 점: libraw의 카메라->출력 색매트릭스
    (output_color)와 화이트밸런스를 **둘 다 우회**한다. Adobe DCP
    프로필의 ColorMatrix1이 요구하는 공간이 바로 이 "카메라 네이티브
    RGB"(디모자이크는 됐지만 색변환/WB 이전)이기 때문 - decode_raw()의
    출력은 libraw가 이미 자기 매트릭스와 WB를 적용한 sRGB 프라이머리
    값이라 DCP에 그대로 쓸 수 없다.

    WB가 안 걸려서 초록 채널이 다른 채널의 약 2배로 치우친 이미지가
    나오는 게 정상이다(베이어 센서의 초록 화소가 2배 많고 초록 감도가
    높기 때문). 차트 검출에는 영향 없음 - chart_baseline.
    detect_and_sample()이 검출용 프리뷰를 만들 때 퍼센타일 정규화를
    거치므로 이 캐스트 상태에서도 검출된다(실측 확인)."""
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=False,
            use_auto_wb=False,
            user_wb=[1.0, 1.0, 1.0, 1.0],
            no_auto_bright=True,
            output_bps=16,
            output_color=rawpy.ColorSpace.raw,
            gamma=(1, 1),  # 순수 linear
        )
    return rgb16.astype(np.float64) / 65535.0


def save_tiff16(rgb_linear, path, apply_srgb_encoding=True):
    """Linear RGB -> 16비트 TIFF 저장.

    apply_srgb_encoding=True(기본)면 sRGB OETF로 감마 인코딩해서 일반
    이미지 뷰어/에디터에서 정상적으로(너무 어둡지 않게) 보이는 파일을
    만든다. False면 순수 linear 값을 그대로 저장 - ΔE 평가나 후속 파이프
    라인에 다시 먹일 때처럼 linear 데이터가 필요한 경우에 쓴다."""
    clipped = np.clip(rgb_linear, 0.0, 1.0)
    if apply_srgb_encoding:
        clipped = colour.cctf_encoding(clipped, function="sRGB")
    u16 = (np.clip(clipped, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    bgr = u16[:, :, ::-1]
    cv2.imwrite(path, bgr)


def save_jpeg8(rgb_linear, path, quality=95):
    """Linear RGB -> sRGB 감마 인코딩 8비트 JPEG 저장. 바로 보고 공유할 수
    있는 "완성본" 출력용 - 후속 편집/재파이프라인 입력이 필요하면
    save_tiff16(apply_srgb_encoding=False)을 대신 쓴다."""
    clipped = np.clip(rgb_linear, 0.0, 1.0)
    encoded = colour.cctf_encoding(clipped, function="sRGB")
    u8 = (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    bgr = u8[:, :, ::-1]
    cv2.imwrite(path, bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])


def load_image_linear(path, resize_to=None):
    """일반 이미지 파일(JPEG/TIFF/PNG 등, 이미 sRGB 감마 인코딩된
    "완성본")을 읽어서 Linear RGB float64 [0, 1]로 되돌린다. ΔE 평가에서
    타깃 이미지(예: 실제 카메라 JPEG)를 엔진 출력과 같은 도메인으로
    맞추기 위한 용도.

    resize_to=(H, W)를 주면 아직 8/16비트 정수인 상태에서(즉 float64
    변환+cctf_decoding으로 몇 배 부풀기 전에) 먼저 리사이즈한다 - 큰
    타깃 이미지를 다운샘플된 엔진 출력과 비교할 때 원본 전체 해상도로
    float64 변환하는 순간의 메모리 스파이크(실측: 105MP에서 OOM)를
    피하기 위함. 호출부가 이미 축소된 크기를 알고 있을 때만 쓴다."""
    bgr = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise FileNotFoundError(path)
    if resize_to is not None and bgr.shape[:2] != tuple(resize_to):
        bgr = cv2.resize(bgr, (resize_to[1], resize_to[0]), interpolation=cv2.INTER_AREA)
    if bgr.dtype == np.uint16:
        rgb = bgr[:, :, ::-1].astype(np.float64) / 65535.0
    else:
        rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def decode_raw_darktable(raw_path):
    """RAW -> Linear RGB, darktable-cli 경유(연구용 전용 -
    decode_raw()를 대체하지 않는다, tools/evaluate_darktable_vs_rawpy.py
    전용). float64 [0, ~) 범위, shape (H, W, 3), RGB 순서,
    decode_raw()와 같은 sRGB(Rec.709) 프라이머리 기준 선형광 값이지만
    데모자이크/카메라 매트릭스/화이트밸런스를 rawpy(LibRaw)가 아니라
    darktable이 계산한다는 점이 다르다.

    subprocess로 darktable-cli를 호출해 32비트 float TIFF로 export한다.
    --icc-type LIN_REC709(선형, Rec.709 프라이머리)와
    plugins/darkroom/workflow=none(filmic/노출 자동보정 끔 - 안 끄면
    darktable 기본값이 톤매핑까지 적용해서 decode_raw()와 비교
    불가능한 결과가 나온다, 직접 확인함)이 핵심이다. darktable 출력은
    음수를 클립하지 않으므로 읽어온 뒤 0으로 클립해서 decode_raw()와
    하한을 맞춘다.

    **호출 프로세스의 OMP_NUM_THREADS를 절대 물려받으면 안 된다** -
    darktable 4.6.1이 이 값을 코어 수보다 작게 설정된 채로 물려받으면
    프레임을 코어 수만큼 스트라이프로 나눠놓고 그중 OMP_NUM_THREADS
    개만 실제로 렌더링해서, 나머지 스트라이프가 전부 새까맣게 나온다
    (에러도 안 나고 종료 코드도 0 - 조용히 잘못된 결과를 냄, 실측
    확인: 이 컨테이너의 4코어에서 OMP_NUM_THREADS=1이면 이미지의
    75%가 검게 잘림). tools/evaluate_darktable_vs_rawpy.py는 rawpy의
    X-Trans 논디터미니즘 때문에 자기 프로세스 환경에
    OMP_NUM_THREADS=1을 설정하는데, 그게 부모→자식으로 그대로
    전달되면서 처음 실제로 벌어진 문제였다 - 그래서 이 함수는 호출자의
    환경과 무관하게 항상 OMP_NUM_THREADS/OMP_THREAD_LIMIT를 지운
    독립된 환경으로 subprocess를 띄운다.

    출력에 대해서도 방어적으로 검증한다 - 위 문제처럼 종료 코드/파일
    존재만으로는 부분 잘림을 못 잡으므로, 완전히 까만(전 채널 0) 행이
    일정 비율을 넘으면 잘린 렌더로 보고 예외를 던진다.

    subprocess+임시파일 기반이라 decode_raw()보다 훨씬 느리다(파일당
    10초 이상) - 프로덕션 경로가 아니라
    tools/evaluate_darktable_vs_rawpy.py 전용이다."""
    env = os.environ.copy()
    env.pop("OMP_NUM_THREADS", None)
    env.pop("OMP_THREAD_LIMIT", None)
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "out.tif")
        result = subprocess.run(
            ["darktable-cli", raw_path, out_path,
             "--icc-type", "LIN_REC709", "--out-ext", "tif",
             "--core",
             "--conf", "plugins/imageio/format/tiff/bpp=32",
             "--conf", "plugins/darkroom/workflow=none"],
            capture_output=True, text=True, env=env,
        )
        if result.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(
                f"darktable-cli failed for {raw_path}: {result.stderr}")
        bgr = cv2.imread(out_path, cv2.IMREAD_UNCHANGED)
        if bgr is None:
            raise RuntimeError(
                f"failed to read darktable-cli output for {raw_path}")
    rgb = bgr[:, :, ::-1].astype(np.float64)
    black_row_fraction = (rgb == 0).all(axis=(1, 2)).mean()
    if black_row_fraction > 0.01:
        raise RuntimeError(
            f"darktable-cli output for {raw_path} looks truncated: "
            f"{black_row_fraction:.1%} of rows are fully black "
            "(likely an OpenMP thread-count mismatch during rendering)")
    return np.clip(rgb, 0.0, None)
