# HNCS

핫셀블라드(Hasselblad) 공식 샘플 이미지를 실측 분석해서 HNCS(Hasselblad
Natural Colour Solution)의 톤/색 특성을 코드로 근사하는 프로젝트.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `hasselblad_hncs.py` | X 시스템(X1D~X2D II) 통합 HNCS 근사 - film curve + 지각보상 대비, hue/채도 무조작 |
| `hasselblad_day.py` | 낮 장면 그레이딩 프리셋 |
| `hasselblad_night.py` | 밤 장면 그레이딩 프리셋 (DR 중앙 압축) |
| `film_sim_presets.py` | 후지필름 스타일 필름 시뮬레이션 프리셋 8종 (Astia, PRO Neg, Eterna, Acros 등) |
| `hasselblad_sample_images.csv` | 공식 샘플 이미지 메타데이터 (카메라/렌즈/작가/jpeg_url/raw_url) |
| `analyze_all_samples.py` | CSV의 jpeg_url 전체를 받아 블랙포인트/화이트포인트/채도 통계 추출 |
| `portrait_skin_analysis.py` | 얼굴 검출(YuNet)로 인물 서브셋 추출 + `apply_hncs` 적용 전/후 피부톤 hue 불변성 검증 |
| `calibrate_from_raw.py` | raw_url이 있는 행을 rawpy로 중립 렌더링해서 진짜 전/후(raw→공식JPEG) 페어 기반 그리드서치 |
| `learn_tone_curve.py` | 같은 raw+jpeg 페어에서 neutral_L→target_L 매핑을 픽셀 단위로 직접 학습해 256단계 LUT 생성 (파라메트릭 커브 가정 없음) |
| `hasselblad_hncs_learned.py` | `learn_tone_curve.py`로 학습한 LUT을 내장한 데이터 기반 대안 - `apply_hncs_learned()` |
| `regularized_lut_loocv.py` | 학습 LUT을 파라메트릭 커브 쪽으로 정규화해보고 10장 leave-one-out 교차검증으로 실제 도움이 되는지 검증 (결론: 정규화 안 하는 게 나음) |
| `face_detection_yunet.onnx` | `portrait_skin_analysis.py`가 쓰는 얼굴 검출 모델 (OpenCV Zoo, YuNet 2023mar) |
| `fetch_fuji_sample_links.py` | mirrorlesscomparison.com의 후지 카메라 리뷰 갤러리에서 "SOOC JPG and RAW" Google Drive 링크를 긁어 `fuji_sample_pages.csv`로 저장 |
| `download_fuji_pairs.py` | 위 링크에서 RAW+JPEG를 받아 EXIF 촬영시각으로 같은 사진끼리 페어 매칭 (`fuji_pairs_manifest.csv`) - 실제로는 페어가 거의 없다는 게 밝혀짐(아래 결론 참고) |
| `analyze_fuji_film_modes.py` | 받은 SOOC JPEG를 실제 Film Mode 태그(exiftool)별로 묶어 population 통계 비교, `film_sim_presets.py`의 프리셋이 실측과 같은 방향으로 채도/톤을 움직이는지 검증 |
| `analyze_leica_samples.py` | imaging-resource.com 카메라 리뷰 갤러리(M9/X Vario/SL2)에서 미편집 SOOC JPEG를 모아 population 통계 추출 (`leica_stats_result.csv`) |
| `leica_color.py` | 위 population 통계로 1차 피팅한 라이카 색감 근사 - `apply_leica_look()` (raw 페어 없이 만든 초기 버전, 아래 한계 참고) |
| `analyze_phaseone_samples.py` | imaging-resource.com Phase One XF 100MP 리뷰 갤러리에서 미편집 SOOC JPEG population 통계 추출 (`phaseone_stats_result.csv`) - EXIF Software가 Capture One이라 "카메라 JPEG"가 아니라 "Capture One 기본 렌더링"이 타깃 |
| `phaseone_color.py` | 위 population 통계로 1차 피팅한 Phase One/Capture One 색감 근사 - `apply_phaseone_look()` |
| `analyze_pentax_samples.py` | imaging-resource.com Pentax 645Z/K-1 리뷰 갤러리에서 미편집 SOOC JPEG population 통계 추출 (`pentax_stats_result.csv`) |
| `pentax_color.py` | 위 population 통계로 1차 피팅한 펜탁스 색감 근사 - `apply_pentax_look()` |
| `analyze_ricoh_gr_samples.py` | imaging-resource.com Ricoh GR III/GR IIIx 리뷰 갤러리에서 population 통계 추출 (`ricoh_gr_stats_result.csv`) - 펜탁스와 같은 EXIF 패턴(리코이미징) |

## 설치

```
pip install -r requirements.txt
```

`.claude/settings.json`은 이 리포에서 Claude Code로 분석 스크립트를 돌릴 때
`cdn.hasselblad.com`, `live.staticflickr.com` 등으로의 네트워크 접근을
자동 허용하는 샌드박스 설정입니다.

## 사용법

```python
import cv2
from hasselblad_hncs import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

`hasselblad_day` / `hasselblad_night`, `film_sim_presets`의 각 `apply_*`
함수도 동일하게 BGR `np.ndarray`를 받아 BGR `np.ndarray`를 반환합니다.

### 실측 재현/재검증

```
python3 analyze_all_samples.py       # 전체 샘플 통계
python3 portrait_skin_analysis.py    # 인물 서브셋 + 피부톤 hue 검증
python3 calibrate_from_raw.py        # raw 기반 진짜 전/후 그리드서치 (rawpy 필요, 대용량 다운로드)
python3 learn_tone_curve.py          # raw+jpeg 픽셀 대응으로 톤커브 직접 학습 (rawpy 필요)
```

## 현재까지의 실측 결론 (v12 기준, `hasselblad_hncs.py` docstring 참고)

- 공식 샘플 124장 통합 풀 기준 블랙p2=11.3, 화이트p99.5=223.9, 인물
  서브셋(43장)은 10.2/226.3 — v8(19~20장) 대비 큰 변동 없음
- 인물 43장 자동 검증에서 `apply_hncs` 적용 전/후 피부톤 hue는 사실상
  불변 (평균 |delta|=0.21, 최대 2.0 / hue 스케일 0~179)
- raw→JPEG 진짜 전/후 페어(10장)로 그리드서치한 결과, 커브에 전역
  노출/감마 보정 단계(`exposure_gamma`)가 없어서 그레이딩 전/후 밝기
  격차를 못 메꾸는 문제를 확인 (v10) → `exposure_gamma` 파라미터 추가,
  극단적 하이키 샘플(오큘러스 실내, 그림자 없음)을 블랙포인트 피팅에서
  제외하고 재탐색 (v11)
- 최종 채택(`apply_hncs`, v11): `white_point=1.0`, `exposure_gamma=0.7`
  반영, `toe_lift`/`shoulder_start`는 원안(0.001/0.78) 유지 —
  RMSE 36.3→23.3 개선. 숄더 시작점을 0.5까지 낮추면 RMSE가 16.5까지
  더 떨어지지만 그림자유효 표본이 8장뿐이라 커브 모양 자체를 바꾸는 건
  과적합으로 보고 보류
- raw 렌더링 베이스라인을 파이프라인상 더 정확해 보이는 linear
  감마(1,1)로 바꿔봤지만 RMSE가 오히려 악화(23.3→28.2) — rawpy 자체
  디모자이크/컬러매트릭스가 핫셀블라드 실제 파이프라인과 다른 알고리즘
  이라 "센서에 더 가깝게" 만드는 게 도움이 안 됨 (음성 결과, 되돌림)
- `apply_hncs_learned` (v12, `hasselblad_hncs_learned.py`): toe/shoulder
  모양을 가정하지 않고 raw+jpeg 페어에서 neutral_L→target_L 매핑을
  픽셀 단위(1,078만 쌍)로 직접 학습 — RMSE 15.4로 파라메트릭(23.3)보다
  더 나음. 다만 raw+jpeg 페어가 10장뿐이라 표본 수 제약은 동일하게 있고,
  8비트 변환 왕복 과정에서 나오는 hue 오차가 `apply_hncs`보다 약간 큼
  (평균 |delta|~3.0/179, 여전히 육안상 무시할 수준)
- 학습 LUT을 표본 부족 우려로 파라메트릭 커브 쪽에 정규화해봤지만, 10장
  leave-one-out 교차검증 결과 정규화 없는 순수 경험적 LUT이 가장 좋음
  (LOO RMSE 14.6, 정규화를 강하게 걸수록 20.7→28.0으로 악화) — bin당
  픽셀 표본이 충분히 많아 분산 문제보다 파라메트릭 커브 자체의 모양
  편향이 더 크기 때문. `apply_hncs_learned`는 정규화 없이 그대로 유지

## 후지필름 (`film_sim_presets.py`)

후지는 카메라에 내장된 필름시뮬레이션(Provia/Astia/Velvia/Classic
Chrome/Pro Neg Std 등) 프리셋이 여러 개 있어서, 핫셀블라드와 다른
검증 방법을 씀: mirrorlesscomparison.com 리뷰 갤러리에서 진짜
미편집 SOOC JPEG를 모으고, exiftool로 읽은 실제 Film Mode 태그별로
population 통계를 비교해서 `film_sim_presets.py`의 각 프리셋이 실측과
같은 방향으로 채도/톤을 움직이는지 확인 (`analyze_fuji_film_modes.py`).

- raw+jpeg 같은 사진 페어를 노려봤지만(`download_fuji_pairs.py`),
  이 사이트의 "RAW samples"와 "SOOC JPG samples" 폴더는 애초에 같은
  촬영을 짝지어 올린 게 아니라 그냥 각각 다른 사진들이었음 - 10개
  카메라, RAW 57장+JPEG 40장을 받았는데 EXIF 촬영시각이 정확히 일치하는
  페어는 3쌍뿐(그마저 다 Provia). raw 기반 캘리브레이션(핫셀블라드
  v10~v12급)은 포기하고 population 비교로 전환.
- 실측(n=8~15) vs `apply_astia`/`apply_pro_neg_std`를 Provia 사진에
  적용했을 때의 방향 비교 결과, 둘 다 실측과 정반대로 채도가 올랐음
  (Astia 실측 -12.9 vs 프리셋 +9.4, Pro Neg Std 실측 -19.4 vs 프리셋
  +11.3). 원인은 톤커브를 BGR 채널에 개별로 걸어서(`apply_lut`) 채널
  간 격차가 벌어지며 채도가 재상승하는 것 (원본 125.0 -> HSV
  desaturation 후 109.4 -> BGR별 커브 후 139.7, 원본보다도 높아짐).
  `apply_hncs.py`처럼 Lab L채널에만 커브를 적용하도록 두 프리셋 다 수정.
- Pro Neg Std는 L채널로 옮긴 뒤에도 여전히 반대 방향이었는데, 커브
  모양 자체가 틀렸던 것으로 판명 - 기존엔 대비를 강조하는 S커브
  (n=1.4)를 썼는데 실측은 Pro Neg Std가 Provia보다 오히려 대비가 낮은
  플랫한 프로파일(블랙p2 +2.7, 화이트p99.5 -19.0)이었음. 대비 완화
  커브(n=0.65)로 교체.
- 수정 후 재검증: Astia 1/3 → 2/3 방향 일치, Pro Neg Std 0/3 → 3/3
  방향 일치.

## 라이카 (`leica_color.py`)

라이카는 후지식 다중 필름시뮬레이션이 없고, 핫셀블라드 공식 킷 같은
raw+jpeg 페어 세트도 못 찾음 (dpreview/kenrockwell/photographyblog는
Cloudflare 봇 차단, stevehuffphoto.com은 Photoshop/Lightroom 편집본이라
SOOC 아님, leicarumors.com이 링크한 DNG는 Dropbox 폴더인데 JS
렌더링이라 목록을 못 긁음 - Fuji 때 Google Drive는 `gdown`으로
우회했지만 Dropbox는 동급 도구가 없었음). 대신 imaging-resource.com
카메라 리뷰 갤러리에서 미편집 SOOC JPEG 45장(M9/X Vario/SL2, exiftool
Software 태그로 Photoshop/Lightroom 편집본 제외)을 모아 population
통계만 냈음 - 핫셀블라드 v8/v9와 같은 급, raw 대비 진짜 전/후 피팅은
아직 없음.

- population 통계(n=45): 블랙p2=9.2, 화이트p99.5=229.8, 채도=98.6.
  카메라별 편차가 커서(SL2 화이트p99.5=192.1 vs M9 251.6) 표본이 더
  모일 때까지 전체 평균을 타깃으로 사용
- `leica_color.py`의 `apply_leica_look()`은 이 population 타깃을
  `_film_curve`의 toe_lift/white_point에 직접 대입해서 만든 1차 버전 -
  raw 기준선이 없어 그리드서치로 피팅한 게 아니고, shoulder_start/
  clahe_clip/hue·채도 무조작 가정은 전부 핫셀블라드 값을 검증 없이
  차용한 것. raw 페어를 구하면 제일 먼저 검증해야 할 부분

## Phase One (`phaseone_color.py`)

Phase One 디지털백은 스튜디오/테더링 중심이라 컨슈머 카메라 같은
인카메라 JPEG 엔진이 사실상 없음 - imaging-resource.com에서 받은 샘플
전부 EXIF Software가 "Capture One"(Phase One 자체 RAW 컨버터)이었음.
그래서 이 프로젝트가 재현하려는 건 "카메라 JPEG"가 아니라 "Capture One
기본 렌더링"이 됨. raw(IIQ) 다운로드 링크는 imaging-resource.com 현재
사이트 템플릿에서 못 찾음(라이카 SL2도 마찬가지였음 - 개편되며 사라진
기능으로 보임) - 라이카와 같은 population 통계 방식으로 접근.

- 1차 실행(n=20)에서 8/20이 ISO 노이즈 테스트 차트(ISO-50~25600, 같은
  장면 반복 촬영)였는데 이게 population을 왜곡시킴 - 채도 평균이 76.9로
  나왔다가 차트 샷을 빼니 118.6으로 확 달라짐. 파일명 "-iso-" 필터를
  추가하고 표본을 30장으로 늘려 재실행
- population 통계(n=30, ISO 차트 제외): 블랙p2=11.4(그림자유효 9장),
  화이트p99.5=228.4, 채도=96.0
- `apply_phaseone_look()`도 leica_color.py와 같은 방식(raw 기준선 없이
  population 타깃을 toe_lift/white_point에 직접 대입) - shoulder_start/
  clahe_clip/hue·채도 무조작 가정 미검증인 것도 동일

## Pentax (`pentax_color.py`)

imaging-resource.com 리뷰 갤러리(645Z 중형포맷 + K-1 풀프레임)에서
미편집 SOOC JPEG 40장을 모음. EXIF Make="RICOH IMAGING COMPANY, LTD."
(펜탁스는 리코이미징 소유 브랜드), Software가 카메라 펌웨어 버전
문자열인 것으로 진짜 SOOC 확인. 이 사이트에서 DNG 링크는 라이카/Phase
One 때와 마찬가지로 못 찾아서 population 통계만 사용.

- population 통계(n=40): 전체 블랙p2=10.8, 화이트p99.5=239.1, 채도=124.1
- 바디별: 645Z(n=20) 블랙p2=10.4/화이트p99.5=247.2/채도=141.1, K-1(n=20)
  블랙p2=11.1/화이트p99.5=231.0/채도=107.1 - 블랙포인트는 거의 같은데
  645Z가 화이트/채도 둘 다 높음. 중형포맷 특성인지 표본(리뷰어 1인)
  편향인지는 미확인, raw 페어 없이는 판단 불가
- `apply_pentax_look()`도 동일한 population-fit 방식, 동일한 미검증
  한계(shoulder_start/clahe_clip/hue·채도 무조작)
