"""
`core/dcp_export.py`의 격리 사본(2026-09-01, 사용자 지시 "파일 복사해서
격리해서 진행") - HueSatMap 태그 지원을 실험하기 위한 것. `core/dcp_export.py`
자체는 Never-list라 손대지 않는다(`hybrid_engine/CLAUDE.md` "Never
touch": `assets/profiles/*.dcp`를 쓰는 코드가 실험적 필드를 만지면
안 됨).

배경: `tools/refit_dcp_irls_cyan_init.py`로 배포된 chart 매트릭스도
patch 17(cyan)에서 a*(녹-적) 축으로 평균 +11.98 치우침(표준편차
0.496 - 노이즈 아님)이 남는다 - `hybrid_engine/EVALUATION.md`의 해당
절 참고. 3x3 선형 매트릭스로는 이 방향의 스펙트럴 메타메리즘을 못
잡는다는 게 진단이었고, DNG의 `ProfileHueSatMapData1`(3x3 매트릭스로는
불가능한 hue별 비선형 보정)이 이론상 다음 단계다.

이 파일은 `core/dcp_export.py`의 `write_dcp()`/`read_dcp()`를 그대로
복사하고 HueSatMap 3개 태그(`ProfileHueSatMapDims`=50937,
`ProfileHueSatMapData1`=50938, `ProfileHueSatMapEncoding`=51107)와
FLOAT 타입 지원만 추가한 것 - 원본 로직은 건드리지 않았다. 실기기
(Lightroom) 검증 없음 - `core/dcp_export.py`가 매직 넘버/UniqueCameraModel
버그를 실기기 테스트 전까지 몰랐던 것과 같은 리스크가 이 신규 태그에도
그대로 있다.

DNG 1.4 스펙(Adobe DNG Specification, "Hue/Saturation/Value Mapping"
섹션) 기준 데이터 레이아웃: (HueDivisions, SatDivisions, ValueDivisions)
그리드의 각 셀에 (hue_shift_deg, sat_scale, val_scale) 3-tuple 하나씩,
value가 가장 빨리 변하고 sat, hue 순으로 바깥쪽 - 인덱스는
`((hue_i * SatDivisions) + sat_i) * ValueDivisions + val_i`, 셀당 3
float. 첫 hue division은 hue=0(적색)에 고정되고 360/HueDivisions
간격으로 나뉜다(스펙 원문).
"""
import struct

import numpy as np

# DNG 스펙 태그 ID (core/dcp_export.py와 동일)
TAG_UNIQUE_CAMERA_MODEL = 50708
TAG_COLOR_MATRIX_1 = 50721
TAG_CALIBRATION_ILLUMINANT_1 = 50778
TAG_PROFILE_NAME = 50936
TAG_PROFILE_HUE_SAT_MAP_DIMS = 50937
TAG_PROFILE_HUE_SAT_MAP_DATA_1 = 50938
TAG_PROFILE_EMBED_POLICY = 50941
TAG_FORWARD_MATRIX_1 = 50964
TAG_PROFILE_HUE_SAT_MAP_ENCODING = 51107

# TIFF 필드 타입
_TYPE_ASCII = 2
_TYPE_SHORT = 3
_TYPE_LONG = 4
_TYPE_SRATIONAL = 10
_TYPE_FLOAT = 11

_TYPE_SIZES = {_TYPE_ASCII: 1, _TYPE_SHORT: 2, _TYPE_LONG: 4,
               _TYPE_SRATIONAL: 8, _TYPE_FLOAT: 4}

_TIFF_MAGIC = 42
_DCP_MAGIC = 0x4352
_RATIONAL_DENOM = 1000000


def _srational_payload(values):
    out = b""
    for v in np.asarray(values, dtype=np.float64).reshape(-1):
        numerator = int(round(float(v) * _RATIONAL_DENOM))
        out += struct.pack("<ii", numerator, _RATIONAL_DENOM)
    return out


def _float_payload(values):
    out = b""
    for v in np.asarray(values, dtype=np.float64).reshape(-1):
        out += struct.pack("<f", float(v))
    return out


def _ascii_payload(text):
    return text.encode("ascii") + b"\x00"


def write_dcp(path, camera_model, profile_name, color_matrix_1,
              calibration_illuminant_1, forward_matrix_1=None,
              hue_sat_map_dims=None, hue_sat_map_data=None,
              hue_sat_map_encoding=None):
    """`core/dcp_export.py`의 `write_dcp()`와 동일 + HueSatMap 3개
    옵션 인자. hue_sat_map_dims: (HueDivisions, SatDivisions,
    ValueDivisions) 3-tuple. hue_sat_map_data: 길이
    HueDivisions*SatDivisions*ValueDivisions*3의 배열(또는 그 모양의
    ndarray), (hue_shift_deg, sat_scale, val_scale) 순서로 flatten.
    hue_sat_map_encoding: 0(선형) 또는 1(sRGB) - DNG 1.4+, 생략 시
    태그 자체를 안 씀(구버전 ACR 호환)."""
    entries = []

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

    entries.append((TAG_PROFILE_EMBED_POLICY, _TYPE_LONG, 1,
                    struct.pack("<I", 0)))

    if forward_matrix_1 is not None:
        entries.append((TAG_FORWARD_MATRIX_1, _TYPE_SRATIONAL, 9,
                        _srational_payload(forward_matrix_1)))

    if hue_sat_map_dims is not None:
        hd, sd, vd = (int(x) for x in hue_sat_map_dims)
        entries.append((TAG_PROFILE_HUE_SAT_MAP_DIMS, _TYPE_LONG, 3,
                        struct.pack("<III", hd, sd, vd)))
        data = np.asarray(hue_sat_map_data, dtype=np.float64).reshape(-1)
        expected_len = hd * sd * vd * 3
        if data.size != expected_len:
            raise ValueError(f"hue_sat_map_data 길이 {data.size} != "
                              f"HueDivisions*SatDivisions*ValueDivisions*3 "
                              f"({expected_len})")
        entries.append((TAG_PROFILE_HUE_SAT_MAP_DATA_1, _TYPE_FLOAT,
                        data.size, _float_payload(data)))
        if hue_sat_map_encoding is not None:
            entries.append((TAG_PROFILE_HUE_SAT_MAP_ENCODING, _TYPE_LONG, 1,
                            struct.pack("<I", int(hue_sat_map_encoding))))

    entries.sort(key=lambda e: e[0])

    ifd_size = 2 + 12 * len(entries) + 4
    data_start = 8 + ifd_size

    ifd = struct.pack("<H", len(entries))
    trailing = b""
    for tag, typ, count, payload in entries:
        if len(payload) <= 4:
            value_field = payload + b"\x00" * (4 - len(payload))
        else:
            value_field = struct.pack("<I", data_start + len(trailing))
            trailing += payload
            if len(trailing) % 2:
                trailing += b"\x00"
        ifd += struct.pack("<HHI", tag, typ, count) + value_field
    ifd += struct.pack("<I", 0)

    with open(path, "wb") as f:
        f.write(struct.pack("<2sHI", b"II", _DCP_MAGIC, 8))
        f.write(ifd)
        f.write(trailing)


def read_dcp(path):
    """`core/dcp_export.py`의 `read_dcp()` + FLOAT 타입 지원 추가."""
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
            if count == 1:
                tags[tag] = struct.unpack_from("<I", payload, 0)[0]
            else:
                tags[tag] = np.array(struct.unpack(f"<{count}I", payload), dtype=np.uint32)
        elif typ == _TYPE_FLOAT:
            tags[tag] = np.array(struct.unpack(f"<{count}f", payload), dtype=np.float64)
        else:
            ints = struct.unpack(f"<{2 * count}i", payload)
            tags[tag] = np.array([ints[2 * j] / ints[2 * j + 1]
                                   for j in range(count)], dtype=np.float64)
    return tags
