"""Adobe DCP(카메라 프로필) 파일 쓰기 - 카메라 네이티브 색매트릭스를
Lightroom Classic/Camera Raw가 읽을 수 있는 형태로 내보낸다.

DCP는 TIFF 구조 파일(리틀엔디안 헤더 + 단일 IFD + DNG 카메라 프로필
태그들)이라 표준 라이브러리 struct로 직접 쓸 수 있다 - Adobe DNG SDK나
추가 의존성이 필요 없다.

core/lut_export.py의 `.cube` 내보내기와 목적이 다르다: `.cube`는 이미
렌더링된 이미지에 얹는 "룩"이고, DCP는 RAW 디모자이크 직후 색변환
단계에 들어가는 색채측정 보정이다. 그래서 DCP에 넣는 매트릭스는 반드시
카메라 네이티브 RGB 공간에서 피팅된 것이어야 한다(설계 근거:
docs/superpowers/specs/2026-07-25-camera-native-matrix-dcp-design.md).

**미검증**: 이 모듈이 만든 파일의 구조 유효성(exiftool 파싱)과 수치
라운드트립은 검증했지만, Lightroom/ACR이 실제로 로드해서 의도한 색을
내는지는 이 프로젝트의 개발 환경에 Adobe 제품이 없어 확인하지 못했다.
프로젝트의 다른 "미검증" 항목들과 같은 성격의 caveat다.

**정정(2026-08-13)**: 실사용자 테스트에서 `hasselblad_x2dii_chart.dcp`가
Lightroom에 안 뜬다는 보고 - exiftool로 파일 자체는 재검증해서 손상
아님을 확인(`Validate: OK`), 원인은 여전히 미확정(설치 경로/Lightroom
재시작 여부/"Camera Matching"은 원래 서드파티가 못 뜨는 카테고리라는
점 등 후보 다수). 상세:
docs/superpowers/specs/2026-07-25-camera-native-matrix-dcp-design.md
"알려진 한계" 3번."""
import struct

import numpy as np

# DNG 스펙 태그 ID
TAG_UNIQUE_CAMERA_MODEL = 50708
TAG_COLOR_MATRIX_1 = 50721
TAG_CALIBRATION_ILLUMINANT_1 = 50778
TAG_PROFILE_NAME = 50936
TAG_FORWARD_MATRIX_1 = 50964

# TIFF 필드 타입
_TYPE_ASCII = 2
_TYPE_SHORT = 3
_TYPE_SRATIONAL = 10

_TYPE_SIZES = {_TYPE_ASCII: 1, _TYPE_SHORT: 2, _TYPE_SRATIONAL: 8}

# SRATIONAL(분자/분모 정수쌍)의 고정 분모. 1e-6 해상도면 색매트릭스
# 계수에 충분하고(계수 크기가 대략 -1~2 범위), int32 범위도 넉넉하다.
_RATIONAL_DENOM = 1000000


def _srational_payload(values):
    """실수 배열을 SRATIONAL 바이트열로. 각 값이 (분자 int32, 분모
    int32) 쌍 8바이트가 된다. 부호 있는 'i'를 쓰는 게 중요하다 -
    색매트릭스는 음수 계수가 흔하다."""
    out = b""
    for v in np.asarray(values, dtype=np.float64).reshape(-1):
        numerator = int(round(float(v) * _RATIONAL_DENOM))
        out += struct.pack("<ii", numerator, _RATIONAL_DENOM)
    return out


def _ascii_payload(text):
    """TIFF ASCII 필드는 NUL 종료 문자열이고 count에 NUL도 포함한다."""
    return text.encode("ascii") + b"\x00"


def write_dcp(path, camera_model, profile_name, color_matrix_1,
              calibration_illuminant_1, forward_matrix_1=None):
    """DCP 카메라 프로필을 path에 쓴다.

    camera_model: UniqueCameraModel - "이 프로필은 어느 카메라용인가".
        이게 없으면 Lightroom이 적용 대상을 판단할 수 없다.
    profile_name: Profile Browser에 표시될 이름.
    color_matrix_1: (3, 3) 또는 길이 9. DNG 정의상 **XYZ(D50) -> 카메라
        네이티브 RGB** 방향이고, **열벡터 규약**이다:
        `color_matrix_1[i][j]`는 `native_col = color_matrix_1 @ xyz_col`
        (표준 행렬-벡터 곱)을 만족하는 3x3의 i행 j열이다.

        **주의 - 전치를 빠뜨리면 조용히 틀린 프로필이 나온다.** 이
        프로젝트의 `hybrid_engine.core.raw_baseline.fit_color_matrix()`는
        **행벡터 규약**으로 피팅한다(`xyz_row ≈ native_row @ M`,
        `apply_color_matrix()`가 `features @ matrix`로 적용하는 것과 같은
        규약). 그 `M`을 여기 넣으려면 역행렬만으로는 부족하고
        **`np.linalg.inv(M).T`** 를 넘겨야 한다. 유도:
        `xyz_row = native_row @ M` 를 전치하면
        `xyz_col = M.T @ native_col` 이고, 이를 뒤집으면
        `native_col = inv(M.T) @ xyz_col = inv(M).T @ xyz_col`.
        `np.linalg.inv(M)`만 넘기면 전치된 매트릭스가 파일에 들어가고,
        구조 검증(exiftool)과 수치 라운드트립은 전부 통과하지만
        Lightroom이 내는 색만 틀리게 된다(실제로 한 번 발생한 버그다 -
        `tests/test_dcp_export.py`의 실제 산출물 회귀 테스트가 잠금).
    calibration_illuminant_1: EXIF LightSource enum(예: 21=D65, 23=D50).
        매트릭스가 어느 백색점 기준으로 피팅됐는지와 반드시 일치해야
        한다 - XYZ(D50) 참조값에 피팅했다면 23(D50)이다.
    forward_matrix_1: 선택. 카메라 네이티브 -> XYZ(D50). DNG 스펙상
        카메라 중립점을 D50 백색점으로 정확히 매핑하는 정규화 제약이
        있는데 그 구현을 Lightroom으로 검증할 수 없어서 기본값은
        None(생략)이다 - 생략해도 유효한 프로필이다."""
    entries = []  # (tag, type, count, payload)

    model_payload = _ascii_payload(camera_model)
    entries.append((TAG_UNIQUE_CAMERA_MODEL, _TYPE_ASCII,
                    len(model_payload), model_payload))

    name_payload = _ascii_payload(profile_name)
    entries.append((TAG_PROFILE_NAME, _TYPE_ASCII,
                    len(name_payload), name_payload))

    entries.append((TAG_CALIBRATION_ILLUMINANT_1, _TYPE_SHORT, 1,
                    struct.pack("<H", int(calibration_illuminant_1))))

    entries.append((TAG_COLOR_MATRIX_1, _TYPE_SRATIONAL, 9,
                    _srational_payload(color_matrix_1)))

    if forward_matrix_1 is not None:
        entries.append((TAG_FORWARD_MATRIX_1, _TYPE_SRATIONAL, 9,
                        _srational_payload(forward_matrix_1)))

    # TIFF 스펙: IFD 엔트리는 태그 오름차순이어야 한다.
    entries.sort(key=lambda e: e[0])

    ifd_size = 2 + 12 * len(entries) + 4  # 엔트리 수 + 엔트리들 + 다음 IFD 오프셋
    data_start = 8 + ifd_size            # 헤더 8바이트 다음이 IFD

    ifd = struct.pack("<H", len(entries))
    trailing = b""
    for tag, typ, count, payload in entries:
        if len(payload) <= 4:
            # 4바이트 이하는 value 필드에 인라인으로 넣는다
            value_field = payload + b"\x00" * (4 - len(payload))
        else:
            value_field = struct.pack("<I", data_start + len(trailing))
            trailing += payload
            if len(trailing) % 2:  # TIFF는 워드 정렬을 요구
                trailing += b"\x00"
        ifd += struct.pack("<HHI", tag, typ, count) + value_field
    ifd += struct.pack("<I", 0)  # 다음 IFD 없음

    with open(path, "wb") as f:
        f.write(struct.pack("<2sHI", b"II", 42, 8))  # 리틀엔디안 TIFF 헤더
        f.write(ifd)
        f.write(trailing)


def read_dcp(path):
    """write_dcp()가 쓴 파일을 되읽어 {태그 ID: 값} dict를 반환한다.
    범용 TIFF 파서가 아니라 이 모듈이 쓰는 세 타입(ASCII/SHORT/
    SRATIONAL)만 다루는 라운드트립 검증용 최소 파서다."""
    with open(path, "rb") as f:
        data = f.read()

    byte_order, magic, first_ifd = struct.unpack_from("<2sHI", data, 0)
    if byte_order != b"II" or magic != 42:
        raise ValueError(f"리틀엔디안 TIFF 헤더가 아님: {byte_order!r}, magic={magic}")

    (n_entries,) = struct.unpack_from("<H", data, first_ifd)
    tags = {}
    for i in range(n_entries):
        off = first_ifd + 2 + 12 * i
        tag, typ, count = struct.unpack_from("<HHI", data, off)
        if typ not in _TYPE_SIZES:
            raise ValueError(f"지원하지 않는 TIFF 필드 타입: {typ} (태그 {tag})")
        size = _TYPE_SIZES[typ] * count
        if size <= 4:
            payload = data[off + 8:off + 8 + size]
        else:
            (payload_offset,) = struct.unpack_from("<I", data, off + 8)
            payload = data[payload_offset:payload_offset + size]

        if typ == _TYPE_ASCII:
            tags[tag] = payload.rstrip(b"\x00").decode("ascii")
        elif typ == _TYPE_SHORT:
            tags[tag] = struct.unpack_from("<H", payload, 0)[0]
        else:
            ints = struct.unpack(f"<{2 * count}i", payload)
            tags[tag] = np.array([ints[2 * j] / ints[2 * j + 1]
                                   for j in range(count)], dtype=np.float64)
    return tags
