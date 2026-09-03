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
"알려진 한계" 3번.

**정정(2026-08-31, 원인 확정)**: 위 미확정 보고, 3주에 걸친 후속 테스트
끝에 원인 2개로 확정됨(Chris Schmauch가 dcpTool로 컴파일해서 실제 동작
확인한 파일을 바이트 단위로 까서 검증) - (1) 이 모듈이 쓰던 헤더 매직
넘버(표준 TIFF 42)가 틀렸다, DCP는 Adobe 전용 매직 `0x4352`가 필요하다
(exiftool은 이 차이를 구조 검증에서 못 잡는다 - 매직을 모르는 파일도
`Validate: OK`를 낸다), (2) `UniqueCameraModel`에 EXIF 문자열이 아니라
Adobe DNG Converter로 실제 RAW를 변환해야 나오는 내부 코드네임이
들어가야 한다. 둘 다 `write_dcp()`/`read_dcp()`에 반영함. 위 줄 4-6의
"표준 TIFF 구조"는 IFD 레이아웃 얘기지 매직 넘버까지 표준이라는 뜻이
아니었다 - 오해의 소지가 있었지만 원 표현은 그대로 두고 여기 정정만
추가한다. 상세:
docs/superpowers/specs/2026-07-25-camera-native-matrix-dcp-design.md.

**검증 완료(2026-08-31)**: 위 두 수정을 반영한 파일을 Chris Schmauch가
Lightroom에서 실제 로드 확인 - 줄 14-17의 "미검증"은 이 두 원인
한정으로는 해소됐다. 이 모듈이 만든 DCP가 Lightroom Profile Browser에
뜨는 것 자체는 이제 실사용자로 검증됨.

**실사용 확인 + 픽셀 비교(2026-09-01)**: Chris Schmauch가 구글 드라이브로
스크린샷과 비교 JPEG 2장을 공유했다. 스크린샷은 Lightroom Classic
Profile Browser에서 이 모듈이 만든 프로필이 **"Camera Matching >
Standard"(Adobe 기본)와 나란히 "Profiles > HNCS X2D II Chart
Colorimetric v4 Adobe"로 정상 분류돼 뜨고, Amount 100으로 실제
적용된 상태**(실제 클라이언트 촬영분,
`B0012548_..._Surprise_Proposal_Photography.3FR`)를 보여준다 - 위
"검증 완료" 항목의 "로드된다"를 훨씬 구체적으로 뒷받침.

같이 온 비교 JPEG 2장("-Camera Standard.jpg" vs "-HNCS+1000K 2.jpg",
같은 소스 사진 `B0012302_..._Family_Portrait_Photography`, 둘 다
Lightroom Classic 15.5 내보내기)을 직접 픽셀 비교(1500px 축소,
`skimage.color.deltaE_ciede2000`):

| 지표 | Camera Standard | HNCS+1000K | 차이 |
|---|---|---|---|
| R/B 비율 | 1.0308 | 1.0489 | +0.0181(더 따뜻하게) |
| Lab b*(청-황) | 130.44 | 131.07 | +0.63(황색 쪽) |
| Lab a*(녹-적) | 128.65 | 128.58 | -0.08 |
| Lab L*(밝기) | 107.75 | 107.01 | -0.74 |

방향은 "+1000K"(Lightroom WB 슬라이더 기준 더 따뜻하게)라는 라벨과
일치. **전체 평균 ΔE00=1.140(표준편차 0.548, 최대 3.899)** - 사람이
겨우 구별하는 문턱(~2.3) 아래라 두 렌더링이 전반적으로 꽤 비슷하고,
차이는 일부 영역에 국한됨. **주의**: 이 비교는 두 Lightroom
내보내기끼리의 차이일 뿐 - "HNCS+1000K"가 카메라 실제 색이나 SOOC
JPEG보다 더 정확하다는 근거는 아니다(참조값 없음, WB를 수동으로 더
얹은 버전이라 오히려 주관적 취향 조정에 가까움). "1000K 정도 낫다"는
인상 자체가 정량적으로 뭘 뜻하는지는 여전히 불명확 - 이 표는 "얼마나
다른지"만 답한다, "더 나은지"는 답하지 않는다."""
import struct

import numpy as np

# DNG 스펙 태그 ID
TAG_UNIQUE_CAMERA_MODEL = 50708
TAG_COLOR_MATRIX_1 = 50721
TAG_COLOR_MATRIX_2 = 50722
TAG_CALIBRATION_ILLUMINANT_1 = 50778
TAG_CALIBRATION_ILLUMINANT_2 = 50779
TAG_PROFILE_NAME = 50936
TAG_PROFILE_EMBED_POLICY = 50941
TAG_FORWARD_MATRIX_1 = 50964
TAG_FORWARD_MATRIX_2 = 50965

# TIFF 필드 타입
_TYPE_ASCII = 2
_TYPE_SHORT = 3
_TYPE_LONG = 4
_TYPE_SRATIONAL = 10

_TYPE_SIZES = {_TYPE_ASCII: 1, _TYPE_SHORT: 2, _TYPE_LONG: 4, _TYPE_SRATIONAL: 8}

# 표준 TIFF/DNG 매직 넘버(리틀엔디안 "II"+42) - RAW/DNG 이미지 파일용.
_TIFF_MAGIC = 42
# Adobe DCP(카메라 프로필) 전용 매직 넘버("IIRC", 바이트로 0x52 0x43 =
# 리틀엔디안 uint16 0x4352). 표준 TIFF 매직이 아니다 - **정정(2026-08-31)**
# 항목 참조.
_DCP_MAGIC = 0x4352

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
              calibration_illuminant_1, forward_matrix_1=None,
              color_matrix_2=None, calibration_illuminant_2=None,
              forward_matrix_2=None):
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
        None(생략)이다 - 생략해도 유효한 프로필이다.
    color_matrix_2, calibration_illuminant_2, forward_matrix_2: 선택,
        dual-illuminant 프로필용(2026-09-03, X2D II 100C combined 챠트
        데이터가 실제로 서로 다른 두 조명을 담고 있다는 게 확인된 뒤
        추가 - `hybrid_engine/EVALUATION.md` "DNG dual-illuminant
        ColorMatrix2" 절 참고). `color_matrix_2`를 주면
        `calibration_illuminant_2`도 필수다(Adobe가 두 매트릭스를
        보간하려면 둘 다 있어야 의미가 있다 - 켤레 없는 매트릭스만
        있으면 그 태그를 그냥 무시한다). 나머지는 `_1` 버전과 동일한
        규약(열벡터, XYZ(D50)->네이티브) - Lightroom/ACR이 촬영 조명을
        추정해서 두 매트릭스 사이를 자체 알고리즘으로 보간한다(정확한
        보간 공식은 Adobe DNG SDK 내부 구현이라 이 프로젝트가 재현한
        것이 아니다 - 실기기 검증 전까지는 근사).

    **정정(2026-08-31)**: 실사용자(Chris Schmauch) 테스트에서 이 함수가
    쓴 파일이 exiftool 구조 검증(`Validate: OK`)과 라운드트립을 전부
    통과하는데도 Lightroom Profile Browser에 계속 안 떴다. 원인 두 가지
    확인됨(dcpTool로 컴파일해서 실제로 동작 확인된 파일을 바이트 단위로
    까서 검증):
    1. **파일 헤더가 표준 TIFF 매직(42)이면 안 된다.** DCP는 RAW/DNG
       이미지 파일과 달리 Adobe 전용 매직 `0x4352`("IIRC")를 요구한다 -
       이 모듈 docstring이 "DCP는 TIFF 구조 파일"이라고 한 건 IFD
       레이아웃 얘기고, 매직 넘버까지 표준이라는 뜻은 아니었다. exiftool은
       이 매직을 모르는 파일은 태그를 하나도 못 읽으면서도 `Validate: OK`
       는 내놓는다 - 그래서 구조 검증으로는 이 버그가 절대 안 잡혔다.
    2. `camera_model`(`UniqueCameraModel`, 아래)에 EXIF `Make`/`Model`
       문자열을 넣으면 Lightroom이 그 카메라의 RAW를 열어도 프로필을
       매칭 대상으로 보여주지 않는다 - Adobe가 DCP 매칭에 실제로 쓰는
       값은 Adobe DNG Converter로 실제 RAW를 변환해봐야 나오는 내부
       코드네임이다(하셀블라드 X2D II 100C의 경우
       `"Hasselblad 100-22-Coated6"`, EXIF `Model`인 `"X2D II 100C"`나
       `Make`+`Model`인 `"Hasselblad X2D II 100C"`가 아니다).
    상세: `docs/superpowers/specs/2026-07-25-camera-native-matrix-dcp-design.md`."""
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

    # dcpTool로 컴파일해서 실제 동작 확인된 파일에 항상 들어있던 태그.
    # 값 0 = "Allow Copying"(가장 permissive한 기본 정책) - dcpTool
    # 기본값을 그대로 따른다, 별도로 고를 이유가 없다.
    entries.append((TAG_PROFILE_EMBED_POLICY, _TYPE_LONG, 1,
                    struct.pack("<I", 0)))

    if forward_matrix_1 is not None:
        entries.append((TAG_FORWARD_MATRIX_1, _TYPE_SRATIONAL, 9,
                        _srational_payload(forward_matrix_1)))

    if color_matrix_2 is not None:
        if calibration_illuminant_2 is None:
            raise ValueError("color_matrix_2를 주려면 calibration_illuminant_2도 필요함")
        entries.append((TAG_CALIBRATION_ILLUMINANT_2, _TYPE_SHORT, 1,
                        struct.pack("<H", int(calibration_illuminant_2))))
        entries.append((TAG_COLOR_MATRIX_2, _TYPE_SRATIONAL, 9,
                        _srational_payload(color_matrix_2)))
        if forward_matrix_2 is not None:
            entries.append((TAG_FORWARD_MATRIX_2, _TYPE_SRATIONAL, 9,
                            _srational_payload(forward_matrix_2)))

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
        # 리틀엔디안 DCP 헤더 - "II" + 0x4352("IIRC"). 표준 TIFF 매직(42)이
        # 아니다, 위 정정(2026-08-31) 참조.
        f.write(struct.pack("<2sHI", b"II", _DCP_MAGIC, 8))
        f.write(ifd)
        f.write(trailing)


def read_dcp(path):
    """write_dcp()가 쓴 파일을 되읽어 {태그 ID: 값} dict를 반환한다.
    범용 TIFF 파서가 아니라 이 모듈이 쓰는 네 타입(ASCII/SHORT/LONG/
    SRATIONAL)만 다루는 라운드트립 검증용 최소 파서다.

    매직 넘버는 `_DCP_MAGIC`(현재 write_dcp()가 쓰는 값)과 `_TIFF_MAGIC`
    둘 다 허용한다 - 이미 커밋된 `hybrid_engine/assets/profiles/*.dcp`가
    정정 전 코드(`_TIFF_MAGIC`)로 쓰여 있어서, 그 파일들을 계속 읽으려면
    둘 다 받아야 한다(2026-08-31 정정 참조)."""
    with open(path, "rb") as f:
        data = f.read()

    byte_order, magic, first_ifd = struct.unpack_from("<2sHI", data, 0)
    if byte_order != b"II" or magic not in (_DCP_MAGIC, _TIFF_MAGIC):
        raise ValueError(f"리틀엔디안 TIFF/DCP 헤더가 아님: {byte_order!r}, magic={magic}")

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
        elif typ == _TYPE_LONG:
            tags[tag] = struct.unpack_from("<I", payload, 0)[0]
        else:
            ints = struct.unpack(f"<{2 * count}i", payload)
            tags[tag] = np.array([ints[2 * j] / ints[2 * j + 1]
                                   for j in range(count)], dtype=np.float64)
    return tags
