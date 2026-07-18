"""
렌즈 왜곡(distortion) 보정 - lensfunpy(lensfun DB, pip 설치만으로 카메라
948종/렌즈 1304종 번들 포함) 기반. EXIF의 Make/Model/LensModel/FocalLength/
FNumber로 DB에서 카메라+렌즈 프로파일을 찾아 지오메트릭 왜곡만 보정한다
(비네팅/색수차는 다루지 않음 - ModifyFlags.DISTORTION으로 범위 한정).

순수 기하 연산(픽셀 재배치)이라 색 파이프라인(core/curve.py 등)과
독립적이고, RAW 디코드 결과든 JPEG 로드 결과든 아무 RGB 배열에나
적용 가능하다.

DB에 카메라/렌즈가 없으면 조용히 원본을 돌려주지 않고 None을 반환한다 -
잘못된(혹은 안 한) 보정을 보정했다고 속이지 않기 위함.
"""
import cv2
import lensfunpy

_DB = None


def _get_db():
    global _DB
    if _DB is None:
        _DB = lensfunpy.Database()
    return _DB


def find_camera(make, model):
    """DB에서 가장 점수 높은(최적 매치) Camera를 반환, 없으면 None."""
    cams = _get_db().find_cameras(make, model, loose_search=True)
    return cams[0] if cams else None


def find_lens(camera, lens_model):
    """주어진 camera 마운트에 맞는 렌즈 중 가장 점수 높은 Lens를 반환,
    없으면 None.

    loose_search=False(엄격 매치)를 쓴다 - loose_search=True는 렌즈명이
    안 맞아도(존재하지 않는 렌즈명이어도) 같은 마운트의 아무 렌즈나
    낮은 점수로 계속 반환해서 "매치 실패"를 조용히 감춰버리기 때문."""
    lenses = _get_db().find_lenses(camera, lens=lens_model, loose_search=False)
    return lenses[0] if lenses else None


def build_modifier(camera, lens, width, height, focal_length, aperture,
                    distance=1000.0):
    """lensfunpy.Modifier 생성 + 초기화. flags=DISTORTION만 켜서 왜곡
    보정 좌표만 계산하도록 범위를 한정한다."""
    modifier = lensfunpy.Modifier(lens, camera.crop_factor, width, height)
    modifier.initialize(focal_length, aperture, distance,
                         flags=lensfunpy.ModifyFlags.DISTORTION)
    return modifier


def undistort(img, modifier):
    """modifier가 계산한 geometry distortion 좌표로 img를 remap.
    보정 데이터가 없는 렌즈면(apply_geometry_distortion이 None 반환) None을
    돌려준다."""
    coords = modifier.apply_geometry_distortion()
    if coords is None:
        return None
    return cv2.remap(img, coords, None, interpolation=cv2.INTER_LANCZOS4)


def correct_from_exif(img, make, model, lens_model, focal_length, aperture,
                       distance=1000.0):
    """EXIF 값으로 DB 조회부터 remap까지 한 번에 수행.

    반환: (corrected_img 또는 None, info dict). info["ok"]가 False면
    corrected_img는 None이고 info["reason"]에 실패 사유(camera_not_found/
    lens_not_found/no_distortion_data)가 담긴다 - 실패를 원본 통과로
    감추지 않는다."""
    camera = find_camera(make, model)
    if camera is None:
        return None, {"ok": False, "reason": "camera_not_found",
                       "make": make, "model": model}

    lens = find_lens(camera, lens_model)
    if lens is None:
        return None, {"ok": False, "reason": "lens_not_found",
                       "camera": camera.model, "lens_model": lens_model}

    height, width = img.shape[:2]
    modifier = build_modifier(camera, lens, width, height, focal_length,
                               aperture, distance=distance)
    corrected = undistort(img, modifier)
    if corrected is None:
        return None, {"ok": False, "reason": "no_distortion_data",
                       "camera": camera.model, "lens": lens.model}

    return corrected, {"ok": True, "camera": camera.model, "lens": lens.model,
                        "focal_length": focal_length, "aperture": aperture}
