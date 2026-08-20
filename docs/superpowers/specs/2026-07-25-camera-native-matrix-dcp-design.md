# 카메라 네이티브 색매트릭스 피팅 + DCP 카메라 프로필 내보내기

## 배경 / 문제

`hybrid_engine/core/chart_baseline.py`와 `tools/analyze_colorchecker_matrix.py`는
기여받은 X2D II ColorChecker Classic 차트 10장으로 "rawpy/libraw 기본
디코드가 참값 색과 얼마나 다른가"를 재고(ΔE00 7.58), 차트로 직접 피팅한
매트릭스로 그걸 2.78까지 줄였다(leave-one-image-out 교차검증). 이건 GitHub
이슈 #4의 지적 4번(uncharacterized raw baseline)에 대한 답이었다.

**그런데 그 매트릭스는 Lightroom/ACR에 넣을 수 있는 형태가 아니다.**
`hybrid_engine/utils/io.py`의 `decode_raw()`는

```python
raw.postprocess(use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB, gamma=(1,1))
```

를 쓴다 - libraw가 **이미** 자기 카메라 색매트릭스와 화이트밸런스를 적용한
결과다. 따라서 기존 차트 매트릭스는 "카메라 센서 RGB → XYZ"가 아니라
**"libraw의 linear sRGB → 참값 linear sRGB"** 보정이다.

Adobe DCP 프로필의 `ColorMatrix1`은 정의상 XYZ(D50) → **카메라 네이티브**
RGB(디모자이크·WB 이전 센서값)다. 기존 매트릭스를 그 자리에 넣으면
Lightroom이 전혀 다른 공간의 값으로 해석해서 **조용히 틀린 색**을 낸다.
(참고: ACR/Lightroom의 Camera Calibration 패널 자체는 3×3 매트릭스를 받는
UI가 아니다 - 레거시 Shadows tint + R/G/B hue·sat 6슬라이더뿐이라, 3×3을
전달할 수 있는 경로는 DCP 파일뿐이다.)

이 스펙은 그 갭을 메운다: 카메라 네이티브 공간에서 매트릭스를 새로 피팅해
검증하고(Phase 1), 그게 libraw 내장 매트릭스를 이길 때만 실제 `.dcp`
프로필로 내보낸다(Phase 2).

## 목표

1. libraw의 색매트릭스·WB를 우회한 **카메라 네이티브 RGB** 디코드 경로를
   추가한다.
2. 그 공간에서 차트 24패치 vs XYZ(D50) 참조값으로 3×3 매트릭스를 피팅하고,
   libraw 내장 `rgb_xyz_matrix`와 leave-one-image-out 교차검증으로 비교한다.
3. 결과(이기든 지든)를 `hybrid_engine/EVALUATION.md`에 기록한다.
4. **교차검증에서 libraw 내장 매트릭스를 이길 때만** 그 매트릭스를 담은
   `.dcp` 파일을 생성한다. 지면 DCP writer 코드는 남기되 프로필 파일은
   배포하지 않는다(사용자 결정 - 프로젝트의 기존 "교차검증 못 넘으면
   기각하고 실패 기록" 관례와 동일).

## 범위 밖

- **기존 `decode_raw()`/`raw_baseline_matrix`/`hasselblad.json` 수정** - 그
  매트릭스는 "카메라 JPEG 룩 근사"라는 다른 목적을 제대로 수행하고 있고
  (이슈 #4 답변에서 이미 확인: 차트 참값에 대고 재면 오히려 나빠지는 게
  정상), 이 스펙은 그것과 병렬인 별개 산출물을 만든다.
- **dual-illuminant DCP** - 조명 조건이 1개뿐이라(아래 한계 1·2) 두 번째
  illuminant를 채울 데이터가 없다. `ColorMatrix2`/`CalibrationIlluminant2`는
  쓰지 않는다.
- **DCP의 LookTable/HueSatMap** - 이건 "룩"이고, 이 스펙의 매트릭스는
  색채측정 정확도용이다. 룩 전달은 이미 `core/lut_export.py`의 `.cube`
  경로가 담당한다.
- **X1D/다른 카메라용 프로필** - 차트 데이터가 X2D II 100C 한 대뿐이다.
- **배치 처리 CLI** - 별도 스펙으로 분리(사용자와 합의).

## 설계

### Phase 1: 카메라 네이티브 매트릭스 (전부 이 환경에서 검증 가능)

#### 1-1. `decode_raw_native()` (`hybrid_engine/utils/io.py`)

```python
raw.postprocess(
    use_camera_wb=False, use_auto_wb=False, user_wb=[1, 1, 1, 1],
    no_auto_bright=True, output_bps=16,
    output_color=rawpy.ColorSpace.raw, gamma=(1, 1),
)
```

`output_color=raw`가 libraw의 카메라→출력 색매트릭스를 우회하고,
`user_wb=[1,1,1,1]`이 WB 곱을 우회한다. 기존 `decode_raw()`는 **건드리지
않는다**(별도 함수 추가).

**검증 완료 사항**(설계 단계에서 실측):
- `rawpy.ColorSpace.raw`가 실재하고 동작한다.
- 출력 채널 평균 (R,G,B) = (0.0498, 0.1068, 0.0496) - WB 미적용이라
  초록이 약 2배로, 카메라 네이티브 공간이 맞다.
- 그 초록 캐스트 상태에서도 기존 `chart_baseline.detect_and_sample()`이
  차트 검출에 **성공**한다. 그 함수가 검출용 프리뷰를 만들 때 이미
  퍼센타일 정규화 + sRGB 인코딩을 거치기 때문 - 즉 detect/sample 경로를
  새로 만들 필요가 없고 기존 함수를 그대로 재사용할 수 있다.

#### 1-2. `reference_patches_xyz_d50()` (`hybrid_engine/core/chart_baseline.py`)

기존 `reference_patches_linear_srgb()`와 같은 colour-science 데이터셋
(`ColorChecker24 - After November 2014`)을 쓰되, 최종 변환 타깃만
XYZ(D50)로 바꾼다. DCP의 기준 공간이 XYZ D50이기 때문이다. 기존 함수는
그대로 두고 나란히 추가한다(기존 ΔE 평가 경로가 계속 sRGB D65를 쓰므로).

#### 1-3. libraw 내장 매트릭스의 방향 실측 확정

rawpy의 `rgb_xyz_matrix`가 XYZ→camera인지 camera→XYZ인지는 문서만으로
단정할 수 없다(실측값: `[[1.0887, -0.6152, 0.1034], [-0.3564, 1.2412,
0.4224], [0.0063, 0.0626, 1.0123]]`, 4번째 행은 0). **추측하지 않고**,
네이티브 샘플에 두 방향(그대로 / 역행렬)을 각각 적용해 XYZ 참조값에
가까워지는 쪽을 채택하고, 두 방향의 ΔE를 리포트에 같이 남겨 판정 근거를
기록한다. 이 판정이 Phase 1 비교의 기준선이 되므로 먼저 확정한다.

#### 1-4. 피팅 + 교차검증

기존 `raw_baseline.fit_color_matrix(sources, targets)`는 소스/타깃이
제네릭이라 그대로 재사용한다(네이티브 RGB를 소스, XYZ D50을 타깃으로).
평가 프로토콜도 기존 `analyze_colorchecker_matrix.py`와 동일하게:

- 기준선 A: libraw 내장 매트릭스(1-3에서 확정한 방향)
- 기준선 B: 보정 없음(네이티브 그대로 XYZ로 간주 - 정상적으로 매우 나쁠
  것이고, 스케일 감각용)
- 후보: 차트 피팅 매트릭스, in-sample + **leave-one-image-out CV**

ΔE는 기존 `patch_delta_e()`와 같은 CIEDE2000이되, XYZ D50 공간에서
Lab으로 가는 경로를 쓴다(D50 백색점 기준). 기존 함수는 sRGB D65 전제라
XYZ 입력을 받는 형태가 필요하면 얇은 헬퍼를 추가한다.

#### 1-5. `tools/analyze_camera_native_matrix.py`

기존 `tools/analyze_colorchecker_matrix.py`와 같은 형태의 실행 스크립트:
비교표를 콘솔에 출력하고 리포트 JSON을
`datasets/hasselblad/contributed/kmichels-x2dii-2026-07/camera_native_matrix_report.json`에
저장한다. 저장할 값: 매트릭스 방향 판정 근거, 세 경우의 이미지별/평균 ΔE,
피팅된 매트릭스, CV 결과.

### Phase 2: DCP 쓰기 (Phase 1에서 이겼을 때만 프로필 배포)

#### 2-1. `core/dcp_export.py`

DCP는 TIFF 구조 파일이라 Python `struct`로 직접 쓸 수 있다 - **새 의존성
0개**. 최소 유효 프로필에 필요한 태그:

| 태그 | ID | 타입 | 값 |
|---|---|---|---|
| `UniqueCameraModel` | 50708 | ASCII | 카메라 모델(어느 카메라용인지 - 없으면 Lightroom이 적용 대상을 모른다) |
| `ProfileName` | 50936 | ASCII | Profile Browser에 뜰 이름 |
| `CalibrationIlluminant1` | 50778 | SHORT | EXIF LightSource enum(아래 한계 1) |
| `ColorMatrix1` | 50721 | SRATIONAL×9 | XYZ(D50) → 카메라 네이티브 = **피팅 매트릭스의 역행렬의 전치**(`inv(M).T`) |

**`ColorMatrix1`에 전치가 필요한 이유**(빠뜨리면 조용히 틀린 프로필이
나온다): `raw_baseline.fit_color_matrix()`는 **행벡터** 규약으로 피팅한다
(`xyz_row ≈ native_row @ M`). 반면 DNG의 `ColorMatrix1`은 **열벡터** 규약
(`native_col = CM1 @ xyz_col`)이다. `xyz_row = native_row @ M`을 전치하면
`xyz_col = M.T @ native_col`이고, 이를 뒤집으면
`native_col = inv(M.T) @ xyz_col = inv(M).T @ xyz_col`. 따라서
`CM1 = inv(M).T`이며, `inv(M)`만 쓰면 전치된 매트릭스가 들어간다.

`ForwardMatrix1`(50964, 카메라 네이티브 → XYZ D50)은 **조건부**로 둔다.
DNG 스펙상 ForwardMatrix는 카메라 중립점을 D50 백색점으로 정확히
매핑해야 하는 정규화 제약이 있는데, 그 정규화를 스펙대로 구현했는지
이 환경에서 Lightroom으로 확인할 방법이 없다. `ColorMatrix1`만 있는
프로필도 유효하므로, 정규화 구현이 라운드트립·수치 검증을 명확히 통과할
때만 `ForwardMatrix1`을 포함하고, 애매하면 **넣지 않는다**(추측해서
넣는 것보다 빼는 게 안전).

#### 2-2. 검증 방법

1. **구조 검증**: `exiftool`(12.76, 설치 확인됨)로 생성 파일을 되읽어
   위 태그가 전부 기대한 값으로 파싱되는지 확인.
2. **라운드트립 수치 검증**: 우리가 쓴 파일을 우리 파서로 되읽어 매트릭스
   값이 SRATIONAL 반올림 오차 내에서 입력과 일치하는지 unittest로 고정.
3. **미검증으로 남는 부분**: Lightroom/ACR이 이 파일을 실제로 로드해서
   의도한 색을 내는지. 이 환경에 Adobe 제품이 없어 증명 불가 - 프로젝트의
   기존 "미검증" 라벨링 관례대로 코드 docstring·README에 명시한다.

## 알려진 한계 (전부 문서화 대상)

1. **장면 조명 복원 불가.** `datasets/.../manifest.csv`의 `illuminant`
   칼럼이 10장 전부 비어있다(이슈 #4에서 "measured illuminant (with the
   illuminant noted)"를 요청했으나 그 항목은 오지 않았다).

   > **정정(2026-07-25, 최종 리뷰 이후)**: 이 항목은 원래 `CalibrationIlluminant1`을
   > `AsShotNeutral`(0.3688, 1, 0.5917)에서 역산한 추정 CCT로 정한다고
   > 적혀 있었다. 구현 후 `.dcp`의 `ColorMatrix1`에서 전치 누락 버그를
   > 잡던 중, 이 역산 자체도 무효였음이 드러났다: `AsShotNeutral`의
   > 채널별 스케일이 `decode_raw_native()` 출력과 일치하지 않아(R×1.11,
   > B×0.83, 무채색 패치 실측으로 확인) CCT 역산이 의미가 없었다. 게다가
   > `reference_patches_xyz_d50()`이 참조값을 D50으로 색순응시킨 뒤
   > 피팅하므로 매트릭스는 애초에 **구성상** D50 기준이라, 촬영 당시 장면
   > 조명은 이 데이터에서 **복원 자체가 불가능**하다(단순히 "측정 안 됨"
   > 보다 강한 진술). 그래서 `CalibrationIlluminant1`은 매트릭스가 실제로
   > 대응하는 참조 백색점인 **23(D50)**으로 고정한다 - 장면 조명을
   > 측정/가정한 값이 아니다. `AsShotNeutral` CCT 역산은 "결론 없음"
   > 진단으로만 리포트 JSON에 남긴다. 상세: `tools/analyze_camera_native_matrix.py`의
   > `_calibration_illuminant()`, `hybrid_engine/EVALUATION.md`의
   > "후속 실측 21".
2. **조명 조건 1개.** 10장 전부 94초 한 버스트다(manifest 기록). 단일
   illuminant 프로필만 만들 수 있고, 조명 간 보간(dual-illuminant)은
   불가능하다.
3. **Lightroom 렌더링 미검증.** 위 2-2의 3번.

   > **정정(2026-08-13, 실사용자 테스트)**: 실제 X2D II 100C 사용자(사진가)에게
   > `hasselblad_x2dii_chart.dcp`를 보내 테스트를 부탁했는데, Lightroom
   > Profile Browser의 "Camera Matching"에 안 뜨고 기본 프로필만 보인다고
   > 보고받음. 재확인한 것: (1) 파일 자체는 손상/잘림이 아님 - `exiftool
   > -validate`가 `Validate: OK`를 반환, `UniqueCameraModel`/`ColorMatrix1`/
   > `CalibrationIlluminant1`/`ProfileName` 4개 태그 전부 정상 파싱됨(190
   > 바이트는 HueSatMap/톤커브 테이블 없는 최소 프로필이라 원래 이 정도
   > 크기가 맞음). (2) 웹 검색으로 확인한 바로는 서드파티 DCP는 Lightroom
   > Profile Browser에서 애초에 "Camera Matching"(Adobe 자체 내장 프로필
   > 전용)이 아니라 별도 카테고리("Custom Profiles" 등)에 뜨는 게 일반적
   > 동작이라, 사용자가 "Camera Matching"에서만 확인했다면 그 자체가
   > 오탐일 수 있음. (3) 설치 경로도 원인 후보 - macOS는
   > `~/Library/Application Support/Adobe/CameraRaw/CameraProfiles/`(중첩
   > 카메라별 서브폴더 아님), 설치 후 Lightroom/ACR을 완전히 재시작해야
   > 반영됨(핫리로드 안 됨) - 이 두 조건 중 하나라도 안 지키면 안 뜬다는
   > 사례가 다수 확인됨(Adobe 커뮤니티 포럼). (4) `UniqueCameraModel`
   > 값("Hasselblad X2D II 100C")은 3FR에 그 태그가 없어서
   > `hybrid_engine/utils/exif.py:read_unique_camera_model()`이 Make+Model
   > 조합으로 대체한 값 - Adobe ACR이 이 카메라를 내부적으로 정확히 같은
   > 문자열로 인식하는지는 Adobe 소프트웨어 없이는 확인 불가, 여전히
   > 미검증. 결론: 파일 자체 손상은 배제됐고, 설치 절차/카테고리 오해
   > 쪽이 유력한 설명이지만 확정은 못 함 - 사용자가 정확한 설치
   > 절차(올바른 폴더 + 재시작)로 재시도한 뒤 재확인 필요.
   >
   > **정정(2026-08-14, 2차 보고로 위 3개 후보 중 2개 배제)**: 사용자가
   > macOS `~/Library/Application Support/Adobe/CameraRaw/CameraProfiles/`에
   > 파일이 정확히 들어있는 스크린샷과 함께 "Lightroom을 여러 번
   > 재시작했지만 어디에도 안 뜨고, 애초에 'Custom Profiles' 섹션 자체가
   > 없다"고 재보고. 이걸로 위 (3)번의 두 후보(잘못된 설치 경로, 재시작
   > 누락)는 배제됨 - "Camera Matching에만 안 뜬다"가 아니라 "커스텀
   > 프로필 섹션 자체가 안 보인다"는 진술이라, "카테고리 오해"
   > 가설(Camera Matching이 아니라 다른 탭에 뜬다)도 약해짐. 파일
   > 자체는 사용자 쪽 사본과 이 저장소의 원본이 바이트 단위로 동일한
   > 190바이트임을 재확인(`ls -la
   > hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp`) - 전송
   > 중 손상 가설도 배제. `Index2.dat`(같은 폴더에 있던 150바이트
   > 파일)이 Adobe의 프로필 인덱스 캐시일 수 있다는 가설을 세우고
   > 웹 검색했으나 이를 뒷받침하는 구체적 정보를 찾지 못함 - **미확인
   > 가설로만 남김, 채택 안 함**. 남은 유일한 미배제 후보는 원래
   > (4)번(`UniqueCameraModel` 문자열 불일치)이고, 소거법상 지금
   > 가장 유력하지만 여전히 직접 확인된 적은 없음. 다음 확인 방법:
   > 사용자에게 실제 X2D II 100C RAW 파일을 Lightroom에서 열어둔
   > 상태에서 Profile Browser를 확인했는지(서드파티 DCP는 매칭되는
   > 카메라의 사진이 열려 있을 때만 노출된다는 게 일반적 ACR 동작),
   > 그리고 그 RAW 파일의 카메라 모델 문자열(예: exiftool
   > `-Model -UniqueCameraModel` 또는 Lightroom 메타데이터 패널)을
   > 물어서 `"Hasselblad X2D II 100C"`와 바이트 단위로 비교하는 것 -
   > 아직 요청하지 않음.
4. **패치 수 부족.** ColorChecker Classic 24패치(무채색 6 + 유채색 18)는
   본격 카메라 프로파일링 타깃(수백 패치)에 비해 매우 적다. 자유도 9개
   매트릭스에 240 패치 샘플(24×10)이라 과적합 위험 자체는 낮지만(기존
   차트 분석에서도 in-sample 2.69 vs CV 2.78로 확인됨), 색공간 커버리지가
   좁아 차트에 없는 색역에서의 정확도는 알 수 없다.
5. **카메라 1대.** X2D II 100C 전용이다. `UniqueCameraModel`로 대상을
   명시하므로 다른 카메라에 잘못 적용될 위험은 없지만, 확장하려면 그
   카메라의 차트 데이터가 필요하다.

## 테스트 계획

**Phase 1** (`tests/test_chart_baseline_native.py` 또는 기존 차트 테스트
파일 확장, unittest 스타일):
- `reference_patches_xyz_d50()`이 (24, 3) 배열을 반환하고, 무채색 패치
  6개의 x,y 색도가 D50 백색점(0.3457, 0.3585) 근처에 모이는지 - 색순응
  타깃이 실제로 D50인지 확인하는 검사.
- `reference_patches_xyz_d50()`과 기존 `reference_patches_linear_srgb()`가
  서로 다른 값을 내는지(같으면 adaptation이 안 걸린 것).
- 합성 데이터 라운드트립: 알려진 3×3을 네이티브 샘플에 곱해 타깃을 만든 뒤
  `fit_color_matrix()`가 그 3×3을 복원하는지(피팅 경로 자체의 정상 동작).
- `decode_raw_native()`는 실 RAW 파일이 필요해 자동 테스트 범위 밖 -
  `tools/analyze_camera_native_matrix.py` 수동 실행으로 확인(이 프로젝트의
  다른 RAW 경로와 동일한 관례).

**Phase 2** (`tests/test_dcp_export.py`):
- 알려진 매트릭스로 `.dcp`를 쓰고, 자체 파서로 되읽어 SRATIONAL 반올림
  오차 내 일치 확인(라운드트립).
- 필수 태그 5개가 전부 존재하고 타입이 맞는지.
- TIFF 헤더/IFD 구조가 유효한지(매직 넘버, 엔디안, IFD 엔트리 수,
  오프셋이 파일 크기 안에 있는지).
- `ForwardMatrix1`을 생략한 경우에도 유효한 파일이 나오는지(조건부 태그).
- exiftool로 읽는 검증은 실행 환경에 exiftool이 있어야 하므로, 수동
  스모크테스트로 수행하고 결과를 리포트에 기록(자동 테스트가 외부 바이너리에
  의존하지 않게).

## 실패 시나리오

Phase 1에서 차트 피팅 매트릭스가 libraw 내장 매트릭스를 교차검증 기준으로
이기지 못하는 경우:

- `EVALUATION.md`에 실측 결과를 그대로 기록한다(삭제하지 않는다).
- `.dcp` 프로필 파일은 생성/배포하지 않는다.
- `decode_raw_native()`·`reference_patches_xyz_d50()`·비교 도구는 코드에
  남긴다 - 향후 더 나은 차트 데이터(다중 조명, 더 많은 패치)가 들어왔을 때
  재시도할 도구로서 가치가 있고, 이 프로젝트의 문서화 철학과 일치한다.
- `core/dcp_export.py`(Phase 2)도 **만들어서 남긴다** - 다만 그 writer로
  실제 `.dcp` 프로필 파일을 생성해 배포하지는 않는다. writer는 매트릭스를
  인자로 받는 범용 도구이므로(특정 매트릭스를 하드코딩하지 않는다) 향후
  더 나은 매트릭스가 나왔을 때 그대로 쓸 수 있고, 라운드트립·구조 검증
  테스트도 합성 매트릭스로 독립적으로 성립한다.
