"""Camera characterization ICC 프로필 쓰기 - Capture One의 Base
Characteristics(Color 탭 → ICC Profile → Import)가 읽는 표준 ICC v4
matrix/TRC 프로필. `core/dcp_export.py`(DCP/Lightroom)와 같은 목적을
다른 회사(Capture One)의 다른 파일 형식으로 낸다.

**DCP와의 핵심 차이**: DCP는 Adobe 전용 TIFF-유사 구조(`_DCP_MAGIC`
매직 + IFD 태그)인 반면, ICC는 공개 표준(ICC.1:2010, v4)이라 구조가
훨씬 엄격하게 명세돼 있다 - 128바이트 고정 헤더 + 태그 테이블 + 태그
데이터. 이 모듈은 그 중 가장 단순한 프로필 종류인 "matrix/TRC" RGB
Input 프로필만 쓴다(전체 색공간을 LUT로 담는 A2B/B2A 타입은 아예 안
씀) - `hybrid_engine`의 챠트 매트릭스 피팅이 이미 만드는 데이터
(3x3 네이티브RGB->XYZ(D50) 매트릭스)와 구조가 그대로 맞아떨어진다.

**입력 공간, DCP와 동일**: `hybrid_engine.utils.io.decode_raw_native()`
가 만드는 화이트밸런스/컬러매트릭스 이전의 카메라 네이티브 선형 RGB -
DCP의 `ColorMatrix1`이 요구하는 것과 같은 공간. 이 함수의 docstring이
명시하듯 화이트밸런스를 우회하므로(`use_camera_wb=False`), 챠트로
피팅한 매트릭스 자체가 WB 불균형까지 같이 흡수한다 - 그래서 TRC는
순수 항등(gamma=1.0, "이미 선형"이라는 뜻)이고 매트릭스 앞에 별도 WB
스케일링을 넣지 않는다. `chart_baseline`이 참조값을 XYZ(D50)로 맞춰서
피팅하므로 PCS 백색점(`wtpt`)도 표준 D50을 그대로 쓴다.

**'chad' 태그는 항등행렬이라도 있어야 한다(2026-09-02, 실측으로 발견)**:
처음엔 wtpt가 이미 D50이니 Bradford 적응용 'chad'(chromaticAdaptationTag)
태그가 필요 없다고 판단하고 뺐는데, littlecms(Pillow의 lcms2 2.17
바인딩)가 `cmsCreateTransform`에서 "cannot build transform"으로
거부했다 - 실제 Adobe/lcms2가 만드는 sRGB 프로필(`ImageCms.createProfile
('sRGB')`를 직접 바이트로 까서 확인)도 wtpt가 이미 D50 상대값인데도
'chad' 태그(`sf32` 타입, 3x3 행렬)를 항상 포함하고 있었다 - v4 RGB
matrix/TRC 프로필 클래스엔 사실상 필수 태그였던 것. 항등행렬로 채워서
추가하니 해결됨(아래 `_TAG_CHAD`/`_sf32_type_payload()`).

**매트릭스 방향 - DCP 전치 버그의 교훈**: DCP의 `ColorMatrix1`은
XYZ(D50)->네이티브 열벡터 방향이라 `chart_m`(행벡터 방향 네이티브->
XYZ)의 `inv().T`가 필요했다(`core/dcp_export.py`의 상세 유도 참고).
ICC의 rXYZ/gXYZ/bXYZ 태그는 정반대로 **네이티브(선형)->XYZ(D50) 열벡터
방향** - `chart_m`이 원래 만들어진 방향과 같다. 유도: `chart_m`은
`xyz_row ≈ native_row @ chart_m`을 만족한다(행벡터 규약). 전치하면
`xyz_col ≈ chart_m.T @ native_col`이고, ICC 스펙 정의(`PCSXYZ = M @
linearRGB_col`, M의 각 열이 rXYZ/gXYZ/bXYZ)와 맞추면 `M = chart_m.T`.
`M[:,0]`(rXYZ) 성분을 풀어보면 `chart_m`의 **0번 행**과 같다 - 즉
전치가 실제로는 "매트릭스 자체를 전치하고 다시 열을 읽는" 게 아니라
**`chart_m`의 각 행이 그대로 rXYZ/gXYZ/bXYZ가 된다**(전치 두 번이
상쇄). 실측 검증(2026-09-02): 하셀블라드 X2D II 무채색 패치 실측
네이티브값(`measured_native_neutral_g_normalized`)을 `chart_m`에
행벡터로 곱하면 D50([0.9642,1.0,0.8249]) 근처([0.959,1.0,0.813])가
나옴 - 방향이 맞다는 증거.

**검증(2026-09-02)**: Pillow의 lcms2 2.17 바인딩으론 여전히 transform
생성이 실패하지만(정확한 원인 미확인 - `chad` 추가로 파싱 자체는
되고 `getProfileDescription()` 등은 통과함), 시스템에 별도 설치된
littlecms 자체 CLI(`transicc`, homebrew, lcms2 **2.19**)로는 완전히
통과한다: `transicc -i hasselblad_x2dii_chart.icc -o "*XYZ" -t1`에
실측 무채색 native RGB를 넣으면 XYZ가 D50 근처로 나온다(Y=1 정규화
[0.959,1.0,0.813], numpy로 직접 계산한 값과 소수점까지 일치) - 이
모듈 코드가 아니라 완전히 독립적인 lcms2 2.19 구현으로 매트릭스
방향/수치를 재확인한 것. Pillow/lcms2 2.17과 시스템 lcms2 2.19 사이의
불일치 자체가 흥미로운 미해결 질문이지만(버전 차이인지 Pillow 바인딩
문제인지 미확인), 최소 하나의 실제 lcms2 구현에서 완전히 동작하는 게
확인됐다.

**실기기(Capture One) 미검증**: 구조/수치는 위처럼 lcms2 2.19로
검증했지만, Capture One이 실제로 로드해서 의도한 색을 내는지는 DCP
초판 때처럼 실사용자 확인 전까지는 모른다 - Capture One의 Base
Characteristics 파이프라인이 정확히 어느 단계에 이 매트릭스를
적용하는지(WB 전/후 등) 공개 스펙이 없어 DNG만큼 확신할 수 없다.

**Never-list 밖**: `hybrid_engine/CLAUDE.md`의 보호 대상은
`assets/profiles/*.json`/`*.dcp`로 확장자가 고정돼 있어 `.icc`는
현재 훅(`protect_never_touch.py`)이 안 잡는다 - 그래도 같은
"배포된 계산 아티팩트" 취급으로 사용자 승인 없이 덮어쓰지 않는다.

**챠트 실측 없는 브랜드용 확장(2026-09-02, 사용자 지시 "소니같은거도
다 매트릭스 만들어")**: `srgb_linear_to_xyz_d50_matrix()`가
Sony/Sigma/Leica처럼 진짜 컬러체커 실측이 없는 브랜드를 위해 추가됐다.
이 브랜드들의 raw+jpeg 매트릭스(`tools/fit_brand_native_matrix_for_icc.py`,
native -> 카메라 JPEG 근사)를 `native_matrix @
srgb_linear_to_xyz_d50_matrix()`로 합성하면 ICC가 요구하는 native ->
XYZ(D50) 형태가 된다 - 다만 **여전히 진짜 컬러체커 실측이 아니라 "그
브랜드 카메라가 내는 JPEG을 흉내" 수준**이다(하셀블라드만 진짜 챠트
데이터 보유). `sony_generic_jpeg_approx.icc`/`sigma_generic_jpeg_approx.icc`/
`leica_generic_jpeg_approx.icc` 파일명의 "jpeg_approx"가 이 구분을
명시한다."""
import datetime
import struct

import numpy as np

# --- DeviceLink(lut8Type, 'mft1') - brands/*.py apply_*() 룩을 캡처원
# 네이티브 형식으로 -----------------------------------------------------
#
# 캡처원은 .cube LUT을 아예 지원 안 한다(공식 임포트 없음, 2026-09-02
# 조사) - 커뮤니티 우회는 LUT을 ICC DeviceLink 프로필로 변환해서 넣는
# 것. matrix/TRC(위)와 달리 DeviceLink는 임의의 룩(HSV 채도/색조 시프트
# 등 3x3 매트릭스로 표현 안 되는 비선형 변환 포함)을 통째로 담을 수
# 있다 - `core/lut_export.py`의 .cube와 정확히 같은 성질(CLAHE 같은
# 공간적응형 변환은 점별 매핑이 아니라서 구조적으로 못 담는 것도
# 동일 - 그 파일 docstring 참고).
#
# lut8Type('mft1') 바이트 구조는 ICC 공식 스펙 PDF가 텍스트 추출이
# 깨져서 실제 참조 구현체(littlecms, `Type_LUT8_Read`/`Write8bitTables`,
# github.com/mm2/Little-CMS의 src/cmstypes.c)를 직접 읽어서 확인했다:
# 1바이트 InputChannels, 1바이트 OutputChannels, 1바이트 CLUTpoints(모든
# 차원 공통 격자 크기), 1바이트 패딩(0), 9개 s15Fixed16Number(3x3
# 매트릭스, InputChannels==3일 때만 적용), 그 다음 InputChannels개의
# 256엔트리 8비트 입력테이블, CLUT 데이터(OutputChannels *
# CLUTpoints^InputChannels 바이트, **마지막 입력채널이 가장 빨리
# 바뀜** - .cube의 R-최우선과 반대 순서, R<->B 스왑 함수를 구워서
# transicc(완전히 독립적인 lcms2 구현)로 라운드트립 검증함), 마지막으로
# OutputChannels개의 256엔트리 8비트 출력테이블.
_TYPE_MFT1 = b"mft1"


def write_icc_devicelink_look_from_lut(path, description, lut_rgb_01, copyright_text="Public Domain"):
    """`core.lut_export.bake_lut_from_function()`이 만드는 (size,size,size,3)
    RGB [0,1] float LUT(.cube와 같은 굽기 함수 재사용 - CLAHE 같은
    적응형 연산을 격자점 하나씩 따로 호출하면 무의미해지는 문제를
    `bake_lut_from_function()`이 이미 정사각형에 가까운 합성 이미지로
    펴서 처리해뒀음, 직접 다시 만들지 않음)를 캡처원 DeviceLink
    ICC(lut8Type/'mft1')로 그대로 굽는다.

    한계: CLAHE 등 공간적응형 변환은 점별 매핑으로 못 담는다 -
    `core/lut_export.py` 모듈 docstring의 같은 한계 참고(이 함수는 그
    한계를 새로 만드는 게 아니라 이미 구운 LUT을 다른 파일 포맷으로
    옮길 뿐). 캡처원 실기기 미검증(exiftool/littlecms 구조 검증만)."""
    size = lut_rgb_01.shape[0]
    if lut_rgb_01.shape != (size, size, size, 3):
        raise ValueError(f"lut_rgb_01은 (size,size,size,3)이어야 함, got {lut_rgb_01.shape}")

    # bake_lut_from_function()의 배열은 lut[b_idx, g_idx, r_idx]로
    # 인덱싱돼 있다(build_identity_grid() docstring, .cube의 "R이 가장
    # 빨리 바뀜" 관례에 맞춘 것) - lut8Type은 반대로 "마지막 입력채널
    # (B)이 가장 빨리 바뀜"을 요구하므로(swap-RB 라운드트립 테스트로
    # 실측 확인) R/B 축을 바꿔서 lut2[r_idx, g_idx, b_idx]로 만든 뒤
    # C-order로 펴야 한다.
    reordered = np.transpose(lut_rgb_01, (2, 1, 0, 3))
    mapped_u8 = np.clip(reordered * 255.0 + 0.5, 0, 255).astype(np.uint8)
    clut_bytes = mapped_u8.reshape(-1, 3).tobytes()

    identity_curve_256 = bytes(range(256))
    payload = (
        _TYPE_MFT1 + b"\x00" * 4
        + struct.pack("BBBB", 3, 3, size, 0)
        + _s15fixed16(1.0) + _s15fixed16(0.0) + _s15fixed16(0.0)
        + _s15fixed16(0.0) + _s15fixed16(1.0) + _s15fixed16(0.0)
        + _s15fixed16(0.0) + _s15fixed16(0.0) + _s15fixed16(1.0)
        + identity_curve_256 * 3  # 입력테이블 3채널(항등)
        + clut_bytes
        + identity_curve_256 * 3  # 출력테이블 3채널(항등)
    )

    tags = [
        (_TAG_DESC, _mluc_type_payload(description)),
        (_TAG_CPRT, _mluc_type_payload(copyright_text)),
        (b"A2B0", payload),
    ]

    header_size = 128
    tag_table_size = 4 + 12 * len(tags)
    data_start = header_size + tag_table_size
    tag_table = struct.pack(">I", len(tags))
    tag_data = b""
    for sig, tag_payload in tags:
        if len(tag_payload) % 4:
            tag_payload = tag_payload + b"\x00" * (4 - len(tag_payload) % 4)
        offset = data_start + len(tag_data)
        tag_table += sig + struct.pack(">II", offset, len(tag_payload))
        tag_data += tag_payload

    profile_size = data_start + len(tag_data)
    now = datetime.datetime.now()
    header = struct.pack(">I", profile_size)
    header += b"\x00" * 4
    header += bytes([4, 0x30, 0, 0])
    header += b"link"
    header += _COLORSPACE_RGB
    header += _COLORSPACE_RGB  # DeviceLink는 PCS 자리에 출력 색공간 시그니처
    header += struct.pack(">HHHHHH", now.year, now.month, now.day,
                           now.hour, now.minute, now.second)
    header += _ACSP_MAGIC
    header += _PLATFORM_APPLE
    header += struct.pack(">I", 0)
    header += b"\x00" * 4
    header += b"\x00" * 4
    header += b"\x00" * 8
    header += struct.pack(">I", 1)
    header += (_s15fixed16(_PCS_ILLUMINANT_D50[0]) + _s15fixed16(_PCS_ILLUMINANT_D50[1])
               + _s15fixed16(_PCS_ILLUMINANT_D50[2]))
    header += b"\x00" * 4
    header += b"\x00" * 16
    header += b"\x00" * 28
    assert len(header) == header_size, len(header)

    with open(path, "wb") as f:
        f.write(header)
        f.write(tag_table)
        f.write(tag_data)

_ACSP_MAGIC = b"acsp"
_DEVICE_CLASS_INPUT = b"scnr"  # 카메라/스캐너(입력 장치) 프로필
_COLORSPACE_RGB = b"RGB "
_PCS_XYZ = b"XYZ "
_PLATFORM_APPLE = b"APPL"

# ICC 스펙이 고정하는 PCS 기준 D50(모든 v4 프로필 헤더에 항상 이 값).
_PCS_ILLUMINANT_D50 = (0.9642, 1.0, 0.8249)

_TAG_DESC = b"desc"
_TAG_CPRT = b"cprt"
_TAG_WTPT = b"wtpt"
_TAG_CHAD = b"chad"
_TAG_RXYZ = b"rXYZ"
_TAG_GXYZ = b"gXYZ"
_TAG_BXYZ = b"bXYZ"
_TAG_RTRC = b"rTRC"
_TAG_GTRC = b"gTRC"
_TAG_BTRC = b"bTRC"

_TYPE_XYZ = b"XYZ "
_TYPE_CURV = b"curv"
_TYPE_MLUC = b"mluc"
_TYPE_SF32 = b"sf32"

_IDENTITY_3X3 = np.eye(3)


def _s15fixed16(value):
    return struct.pack(">i", int(round(float(value) * 65536)))


def _u8fixed8(value):
    return struct.pack(">H", int(round(float(value) * 256)))


def _xyz_type_payload(xyz):
    x, y, z = xyz
    return _TYPE_XYZ + b"\x00" * 4 + _s15fixed16(x) + _s15fixed16(y) + _s15fixed16(z)


def _identity_curve_payload():
    """curveType, count=1, gamma=1.0(u8Fixed8Number) - "이미 선형"이라는
    뜻(스펙상 count=1은 순수 감마 커브, gamma=1.0은 항등변환)."""
    return _TYPE_CURV + b"\x00" * 4 + struct.pack(">I", 1) + _u8fixed8(1.0)


def _sf32_type_payload(matrix_3x3):
    """s15Fixed16ArrayType - 'chad'(chromaticAdaptationTag)에 쓴다.
    row-major 9개 s15Fixed16Number."""
    out = _TYPE_SF32 + b"\x00" * 4
    for v in np.asarray(matrix_3x3, dtype=np.float64).reshape(-1):
        out += _s15fixed16(v)
    return out


def _mluc_type_payload(text, lang=b"en", country=b"US"):
    """multiLocalizedUnicodeType - desc/cprt에 쓰는 v4 표준 타입.
    레코드 1개(단일 언어), UTF-16BE 문자열."""
    utf16 = text.encode("utf-16-be")
    header = _TYPE_MLUC + b"\x00" * 4
    header += struct.pack(">II", 1, 12)  # numRecords=1, recordSize=12
    record_offset = 16 + 12  # mluc 헤더(16) + 레코드 테이블(12) 이후
    header += lang + country + struct.pack(">II", len(utf16), record_offset)
    return header + utf16


def srgb_linear_to_xyz_d50_matrix():
    """표준 sRGB(D65) 선형 RGB -> XYZ(D50) Bradford 적응 매트릭스(행벡터
    규약, `colour-science`로 계산) - 챠트 실측이 없는 브랜드의 raw+jpeg
    매트릭스(native -> sRGB_linear, 카메라 JPEG 근사)를 ICC가 요구하는
    native -> XYZ(D50)로 합성할 때 쓴다: `combined = native_to_srgb_matrix
    @ srgb_linear_to_xyz_d50_matrix()`. **주의**: 이렇게 합성한 프로필은
    하셀블라드 챠트 프로필과 달리 진짜 컬러체커 실측이 아니라 "카메라
    JPEG 근사"다 - `tools/fit_brand_native_matrix_for_icc.py` 참고."""
    import colour
    D50 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]
    srgb = colour.RGB_COLOURSPACES["sRGB"]
    basis = np.eye(3)
    return colour.RGB_to_XYZ(basis, srgb, D50, chromatic_adaptation_transform="Bradford",
                              apply_cctf_decoding=False)


def write_icc_matrix_trc_profile(path, native_to_xyz_d50_matrix, description,
                                  copyright_text="Public Domain"):
    """카메라 네이티브 선형 RGB -> XYZ(D50) 3x3 matrix/TRC ICC 프로필을
    path에 쓴다.

    native_to_xyz_d50_matrix: (3, 3). **행벡터 규약** -
    `xyz_row ≈ native_row @ native_to_xyz_d50_matrix` (이 모듈의
    `chart_matrix_in_sample_irls_cyan_init` 같은 `hybrid_engine` 챠트
    피팅 결과와 동일 규약, 변환 불필요 - 모듈 docstring의 "매트릭스
    방향" 절 참고: 각 행이 그대로 rXYZ/gXYZ/bXYZ가 된다).
    description: Base Characteristics 목록에 뜰 이름.
    copyright_text: cprt 태그 내용, 기본값은 저작권 주장 없음."""
    m = np.asarray(native_to_xyz_d50_matrix, dtype=np.float64)
    if m.shape != (3, 3):
        raise ValueError(f"native_to_xyz_d50_matrix는 (3,3)이어야 함, got {m.shape}")

    tags = [
        (_TAG_DESC, _mluc_type_payload(description)),
        (_TAG_CPRT, _mluc_type_payload(copyright_text)),
        (_TAG_WTPT, _xyz_type_payload(_PCS_ILLUMINANT_D50)),
        (_TAG_CHAD, _sf32_type_payload(_IDENTITY_3X3)),
        (_TAG_RXYZ, _xyz_type_payload(m[0, :])),
        (_TAG_GXYZ, _xyz_type_payload(m[1, :])),
        (_TAG_BXYZ, _xyz_type_payload(m[2, :])),
        (_TAG_RTRC, _identity_curve_payload()),
        (_TAG_GTRC, _identity_curve_payload()),
        (_TAG_BTRC, _identity_curve_payload()),
    ]

    header_size = 128
    tag_table_size = 4 + 12 * len(tags)
    data_start = header_size + tag_table_size

    tag_table = struct.pack(">I", len(tags))
    tag_data = b""
    for sig, payload in tags:
        if len(payload) % 4:
            payload = payload + b"\x00" * (4 - len(payload) % 4)
        offset = data_start + len(tag_data)
        tag_table += sig + struct.pack(">II", offset, len(payload))
        tag_data += payload

    profile_size = data_start + len(tag_data)
    now = datetime.datetime.now()

    header = struct.pack(">I", profile_size)
    header += b"\x00" * 4  # CMM type - 미지정
    header += bytes([4, 0x30, 0, 0])  # version 4.3.0.0
    header += _DEVICE_CLASS_INPUT
    header += _COLORSPACE_RGB
    header += _PCS_XYZ
    header += struct.pack(">HHHHHH", now.year, now.month, now.day,
                           now.hour, now.minute, now.second)
    header += _ACSP_MAGIC
    header += _PLATFORM_APPLE
    header += struct.pack(">I", 0)  # profile flags
    header += b"\x00" * 4  # device manufacturer - 미지정
    header += b"\x00" * 4  # device model - 미지정
    header += b"\x00" * 8  # device attributes
    header += struct.pack(">I", 1)  # rendering intent: relative colorimetric
    header += (_s15fixed16(_PCS_ILLUMINANT_D50[0]) + _s15fixed16(_PCS_ILLUMINANT_D50[1])
               + _s15fixed16(_PCS_ILLUMINANT_D50[2]))
    header += b"\x00" * 4  # profile creator - 미지정
    header += b"\x00" * 16  # profile ID - 계산 안 함(스펙상 선택)
    header += b"\x00" * 28  # reserved

    assert len(header) == header_size, len(header)

    with open(path, "wb") as f:
        f.write(header)
        f.write(tag_table)
        f.write(tag_data)
