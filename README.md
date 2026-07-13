# HNCS

카메라/디지털백 제조사별 공식(또는 공식에 준하는) 샘플 이미지를 실측
분석해서 각 브랜드의 색과학을 코드로 근사하는 프로젝트. 원래 핫셀블라드
HNCS(Hasselblad Natural Colour Solution) 하나만 다뤘는데, 같은 방법론을
후지/라이카/Phase One/Pentax/Ricoh GR로 확장하면서 브랜드별 파일이
늘어나 아래 구조로 정리했다.

## 구조

```
brands/       브랜드별 색감 근사 함수 (apply_*)
core/         브랜드 전체가 공유하는 톤커브/LUT/통계/검증 헬퍼
datasets/     커밋된 참조 CSV (공식 샘플 메타데이터, 스크레이핑한 갤러리 링크)
tools/        분석(analyze)/다운로드(download)/캘리브레이션(calibrate) 스크립트
models/       얼굴 검출 등에 쓰는 사전학습 모델
```

| 파일 | 역할 |
|---|---|
| `brands/hasselblad.py` | ⭐ 공식 Stable - `apply_hncs`(X 시스템 통합 HNCS 파라메트릭 근사) |
| `brands/hasselblad_learned.py` | Experimental - `apply_hncs_learned` (raw+jpeg 페어에서 직접 학습한 LUT, RMSE는 더 낮지만 표본 10장) |
| `brands/hasselblad_day.py` / `brands/hasselblad_night.py` | Legacy - `apply_hasselblad_day`/`apply_hasselblad_night` (day/night 타깃이 apply_hncs 전체 population 타깃에 수렴 중이라 유지 근거 약해지는 중) |
| `brands/fuji.py` | 후지필름 스타일 필름 시뮬레이션 프리셋 9종 (Astia, PRO Neg, Eterna, Acros, Classic Negative 등) - Astia/Pro Neg Std/Eterna Bleach Bypass/Classic Negative는 실측 검증됨 |
| `brands/leica.py` | 라이카 색감 근사 - `apply_leica_look()` (population-fit 1차 버전) |
| `brands/phaseone.py` | Phase One(Capture One 기본 렌더링) 색감 근사 - `apply_phaseone_look()` |
| `brands/pentax.py` | Pentax 색감 근사 - `apply_pentax_look()` |
| `brands/ricoh_gr.py` | Ricoh GR 색감 근사 - `apply_ricoh_gr_look()` |
| `brands/canon.py` | Canon 색감 근사(EOS R5/R6/R8/R3/R 5바디 population) - `apply_canon_look()` |
| `brands/nikon.py` | Nikon 색감 근사(Z6/Z6 II/D780 3바디 population - Z9/D850 갤러리는 EXIF 빠진 자리표시자 이미지뿐이라 제외) - `apply_nikon_look()` |
| `brands/sony.py` | Sony 색감 근사(A7/A7R/A7S/A7 III/A7 IV 5바디 population, 바디당 23장) - `apply_sony_look()` |
| `core/curve.py` | 톤커브 수학 (`film_curve`/`s_curve`/`apply_highlight_rolloff`/`shadow_lift`) - 여러 브랜드 모듈이 공유 |
| `core/lut.py` | LUT 적용 헬퍼 |
| `core/engine.py` | population-fit 브랜드(leica/phaseone/pentax/ricoh_gr) 공용 엔진 - 네 브랜드 모두 raw 기준선 없이 population 타깃을 `film_curve`에 직접 대입하는 동일 구조라 하나로 합침 |
| `core/stats.py` | population 통계 계산 (`image_stats`: 블랙p2/화이트p99.5/채도/그림자비율) |
| `core/validation.py` | "진짜 미가공 SOOC인가" EXIF 검증, "실제로 온전히 디코드되는가" 무결성 검증(`is_image_usable`), hue 측정 헬퍼 |
| `core/denoise.py` | 노이즈 제거 (`denoise()`: nlm/bilateral) - 고ISO 샘플을 브랜드 룩 적용 전에 정리할 때 씀 |
| `datasets/hasselblad/hasselblad_sample_images.csv` | 핫셀블라드 공식 샘플 메타데이터 (카메라/렌즈/작가/jpeg_url/raw_url) |
| `datasets/fuji/fuji_sample_pages.csv` | mirrorlesscomparison.com 후지 갤러리의 RAW/JPEG Google Drive 링크 |
| `datasets/fuji/fuji_imaging_resource_filmmodes.json` | imaging-resource.com X100V/X-T5/X-T4 리뷰 갤러리에서 모은 269장, exiftool FilmMode 태그 포함(Velvia/Provia/Classic Negative/Bleach Bypass/Classic Chrome) - Eterna Bleach Bypass 재보정과 Classic Negative 신규 프리셋의 근거 데이터 |
| `datasets/<brand>/{tone,color,texture,gamut}_signature.json` + `joint_distribution.npz` | 픽셀 단위 5종 시그니처 분석(hasselblad/leica/pentax/ricoh_gr/phaseone/canon/sony/nikon 전부 있음) - 톤/채도-hue/샤프닝-미세대비-노이즈-에지헤일로/Lab 색역, 사진 단위 동일가중 평균 방법론(픽셀 그대로 풀링하면 해상도 편차로 왜곡됨 - `tone_signature.json`의 methodology 필드 참고). **주의**: texture의 sharpening/micro_contrast는 브랜드별로 원본 계산 스크립트가 커밋에 안 남아있어 에이전트마다 공식을 다시 추정하면서 스케일이 갈렸음 - Sony의 sharpening은 최초 계산이 15~20배 커서 Canon 공식(/15)에 맞춰 재계산했고, Canon/Sony의 micro_contrast(DoG sigma 1,2)는 Nikon/Leica/Pentax/Ricoh GR(sigma 1,4 추정, 8~12대)과 자릿수가 달라 서로 직접 비교하면 안 됨(각 브랜드 `.py` docstring과 `texture_signature.json`의 methodology 필드에 상세 기록) |
| `tools/analyze.py` | population 통계/검증 CLI - `hasselblad`/`leica`/`phaseone`/`pentax`/`ricoh_gr`/`fuji_film_modes`/`portrait` 모드 |
| `tools/download.py` | imaging-resource.com 갤러리 공용 스크레이퍼 + 후지 Google Drive RAW/JPEG 페어 다운로더 |
| `tools/calibrate.py` | 핫셀블라드 raw+jpeg 페어 캘리브레이션 CLI - `grid_search`/`learn_curve`/`regularize` 모드 |
| `tools/denoise.py` | 노이즈 제거 CLI - `python3 -m tools.denoise input.jpg output.jpg [--strength N] [--method nlm\|bilateral]` |
| `models/yunet.onnx` | 얼굴 검출 모델 (OpenCV Zoo, YuNet 2023mar) - `tools/analyze.py portrait`가 사용 |

## 이미지 신뢰성 정책 (2026-07~)

imaging-resource.com의 media CDN이 여러 카메라 리뷰 갤러리에서 원본
파일 자체를 손상된 채로 저장하고 있는 걸 발견했다(Hasselblad X2D 100C
갤러리 72%, Phase One XF 100MP 갤러리 100%, Pentax 645Z/K-1 갤러리
40%가 디코드 도중 멈추고 나머지가 빈 채로 저장돼 있었음 - 재다운로드를
여러 방식으로 반복해도 똑같이 재현돼서 전송 문제가 아니라 사이트에
저장된 파일 자체의 결함으로 확인). `cv2.imread()`는 이런 파일도
"Premature end of JPEG file" 경고만 띄우고 나머지를 검은 픽셀로 채운 채
조용히 "성공"해버려서 로드 성공 여부나 shape만으로는 못 거른다.

**그래서 이제부터 모든 population 분석은 `core/validation.py`의
`is_image_usable()`(행 단위 표준편차로 손상 여부 판정)을 통과한
이미지만 쓴다.** `tools/analyze.py`의 모든 다운로드 경로(핫셀블라드
공식 CDN + imaging-resource.com 4개 브랜드)와 `tools/download.py`의
후지 Google Drive 다운로드 경로(`download_fuji_pairs()`) 전부에 이미
적용돼 있어 앞으로 새로 스크레이핑하는 이미지는 자동으로 걸러진다.

기존에 커밋된/캐시된 population 데이터를 전부 재검증한 결과:
  - Leica(45장), Fuji(mirrorlesscomparison.com, 10개 바디 40장 JPEG):
    손상 0장 - 수치 변경 없음
  - Ricoh GR: 기존 40장(GR III+IIIx) 손상 0장. 이후 GR/GR II 갤러리를
    추가로 찾아 n=80으로 확대(GR II의 HDR on/off 비교샷은 필터링) -
    재검증된 수치로 교체
  - Pentax(40장 중 16장 손상): 재수집으로 n=40 유지, 재검증된 수치로 교체
  - Phase One(30장 중 30장 전부 손상): 갤러리 전체(110장 후보)를
    재수집했지만 91장이 또 손상이라 n=16으로 축소, 재검증된 수치로 교체
    (표본 확대를 위해 Phase One XT 갤러리도 시도했으나 살아남은 이미지가
    전부 흑백 전용 Achromatic 백이라 컬러 population에는 못 써서 제외)
자세한 수치는 각 브랜드 파일 docstring 참고.

## 브랜드 함수 QA 검증 (2026-07)

Canon/Sony/Nikon 추가 후 `brands/*.py`의 모든 `apply_*` 함수(핫셀블라드
4종 + 후지 프리셋 9종 + 라이카/Phase One/Pentax/Ricoh GR/Canon/Sony/
Nikon 7종, 총 20개)를 랜덤 BGR 배열에 돌려 shape/dtype이 그대로
보존되는지 스모크테스트함. 전부 정상 동작 확인 - 발견된 버그 없음
(주의: `apply_acros`/`apply_monochrome`은 설계상 1채널 그레이스케일을
반환하므로 shape 비교 시 별도 취급 필요, `core.curve`/`core.lut`에서
`fuji.py`로 재노출된 `apply_highlight_rolloff`/`apply_lut`은 브랜드
프리셋이 아니라 범용 헬퍼라 이 테스트 대상이 아님).

**진행 중**: Canon/Sony/Nikon도 나머지 5개 브랜드처럼 픽셀 단위 5종
시그니처 분석(tone/color/texture/gamut/joint_distribution)으로
확장하는 작업과, 이 세 브랜드를 raw 기준선 있는 캘리브레이션(핫셀블라드
급)으로 업그레이드할 수 있는 raw+jpeg 페어 소스를 찾는 리서치를
백그라운드로 진행 중 - 완료되면 이 섹션과 브랜드별 문단을 갱신할 예정.

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
from brands.hasselblad import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

`brands/*.py`의 각 `apply_*` 함수는 전부 동일하게 BGR `np.ndarray`를
받아 BGR `np.ndarray`를 반환합니다. 리포 루트에서 실행해야 `core`/`brands`/
`tools` 임포트 경로가 맞습니다.

### 실측 재현/재검증

```
python3 -m tools.analyze hasselblad       # 핫셀블라드 공식 샘플 전체 population 통계
python3 -m tools.analyze portrait         # 인물 서브셋 + 피부톤 hue 불변성 검증
python3 -m tools.analyze leica            # 라이카 imaging-resource.com population
python3 -m tools.analyze phaseone         # Phase One 〃
python3 -m tools.analyze pentax           # Pentax 〃
python3 -m tools.analyze ricoh_gr         # Ricoh GR 〃
python3 -m tools.analyze fuji_film_modes  # 후지 Film Mode별 population + 프리셋 방향 검증

python3 -m tools.download fuji-links      # 후지 RAW/JPEG Google Drive 링크 수집
python3 -m tools.download fuji-pairs      # 위 링크에서 RAW+JPEG 페어 다운로드 (gdown 필요)

python3 -m tools.calibrate grid_search    # 핫셀블라드 raw 기반 진짜 전/후 그리드서치 (rawpy 필요, 대용량 다운로드)
python3 -m tools.calibrate learn_curve    # raw+jpeg 픽셀 대응으로 톤커브 직접 학습 (rawpy 필요)
python3 -m tools.calibrate regularize     # 학습 LUT 정규화 + leave-one-out 교차검증
```

## 현재까지의 실측 결론 (v12/day-night v3 기준, `brands/hasselblad.py` docstring 참고)

- **픽셀 단위 5종 시그니처 분석(2026-07, 공식 샘플 124장 전량 진짜 원본)**:
  `datasets/hasselblad/{tone,color,texture,gamut}_signature.json` +
  `joint_distribution.npz`로 저장. 진짜 원본(리사이즈/재인코딩 없음) 기준
  픽셀 단위로 톤/채도-hue/샤프닝-노이즈-헤일로/Lab a·b 색역을 전수 계산.
  - **전체 픽셀을 그냥 풀링해서 percentile을 구하면 안 된다는 걸 실측으로
    확인**: 124장 해상도가 30만~2억 픽셀로 최대 676배 차이나서, 픽셀
    풀링 방식은 큰 사진 몇 장에 통계가 지배당함(풀링 b2=1.0으로 급락,
    사진당 동일가중 평균은 b2=18.1 - 10배 이상 차이). population 타깃은
    "사진 단위 동일가중 평균"으로 계산해야 함 - 풀링 히스토그램 자체는
    `joint_distribution.npz`에 그대로 남겨뒀지만 타깃으로는 안 씀.
  - **캐시(downloaded_samples/, resize+재인코딩) vs 진짜 원본을 124장
    전부 1:1로 재검증**: 그림자유효(dark_pct>5%) 94장 기준 블랙p2
    11.27(캐시) vs 10.63(원본) - 차이 0.6, 5.7%. 화이트p99.5
    223.85(캐시) vs 225.56(원본) - 차이 1.7, 0.8%. 둘 다 노이즈 수준의
    차이라 **캐시가 톤 커브 보정 타깃(b2/w995)을 왜곡시키지는 않았음을
    확인** - v9/apply_hncs가 근거한 기존 타깃(11.3/223.9)은 유효함.
    (참고: 이 재검증 과정에서 파일 인덱스 매핑 실수로 "캐시 vs 원본이
    60% 차이난다"는 오판을 한 번 냈다가, 124장 전부 1:1 재대조해서
    바로잡음 - 위 최종 수치가 맞는 값)
  - **결론: `apply_hncs`/day-night 파라미터에 수정 사항 없음.** 톤
    타깃은 이미 정확했고, 채도/hue/텍스처/색역(color/texture/gamut
    시그니처)은 HNCS가 애초에 안 건드리는 채널이라 "타깃"이 아니라
    population이 실제로 어떤 값을 갖는지 기록하는 참고 자료로만 저장.
- **파이프라인 시그니처 분석(2026-07, 공식 샘플 124장 전량 진짜 원본 재다운로드)**:
  `downloaded_samples/`(자체 캐시: resize+재인코딩으로 노이즈 지표를 왜곡시킴)를
  거치지 않고 124장 전부 `curl`로 무가공 원본을 새로 받아(`/tmp/true_originals/`,
  4.5GB) 샤프닝 강도/미세대비/노이즈/에지 헤일로/JPEG 압축 특성을 측정.
  다운로드 URL 목록에 이전 5장짜리 파일럿 표본과 18장이 중복돼 있어
  제거(105장 고유). 단, 실제 population 통계·day/night v3 보정에 쓰인
  `orig_*.jpg`(124장, CSV 행과 1:1) 자체에는 내부 중복이 전혀 없음을
  재확인 — 기존 재보정 결과는 안전.
  - JPEG 품질: 77%(81/105)가 Q99·YCbCr 4:4:4(사실상 무손실), 소수
    (17장)만 Q75·4:2:0(초기 X1D 계열로 보이는 파일명). 브랜드 필터 자체는
    JPEG로 재인코딩하지 않으므로 이 값은 참고용 메타데이터.
  - 샤프닝 에너지(고주파 평균절대값, 중앙값 2.65)와 미세대비(DoG std,
    중앙값 6.37)는 서로 강하게 상관(r=0.77) — 일관된 로컬 대비 처리
    스타일이 있다는 신호. 그러나 이 값들은 "가공 안 된 원본"과의 짝
    비교가 아니라 완성 JPEG끼리의 자기참조 통계라서, 중립 렌더 대비
    얼마나 강한지 정량화할 기준선이 없음 → 커브 모듈에 별도 샤프닝
    파라미터를 새로 추가할 근거로 쓰기엔 부족하다고 판단, 반영 보류
  - 에지 헤일로(overshoot): 품질 구간별 중앙값은 사실상 평탄(7~8%,
    Q<=80/81-95/>95 전부 비슷) — 5장 파일럿에서 보였던 "저품질일수록
    헤일로 큼" 패턴은 표본을 키우니 사라짐(평균이 튀는 건 소수 극단치
    때문, 중앙값 기준으론 무관). 샤프닝 에너지와의 상관도 약함(r=0.24).
    극단치(orig_133 129.9%, orig_68 45.6% 등)는 실제 스펙큘러 하이라이트
    경계를 halo로 오검출한 것으로 보임 — 이 지표는 JPEG 링잉/진짜 halo/
    장면 자체의 밝은 반사를 못 가른다는 기존 caveat 그대로 확인됨.
    → 헤일로 기반 파라미터도 반영 보류
  - 노이즈: 파일별 편차가 극단적(0.001~6.6)이고 서브샘플링 그룹별
    평균이 서로 겹치는 범위(4:2:0 0.34 / 4:4:4 1.19 / 4:2:2 0.32,
    n=7~81)라 크로마 서브샘플링이나 JPEG 품질로 설명되지 않음 — 장면
    콘텐츠(ISO, 조도, 텍스처) 의존이라는 기존 결론 재확인. 브랜드
    전역에 적용할 고정 그레인/디노이즈 파라미터를 새로 만들 근거 없음
  - **결론**: 표본을 124장 전량으로 늘려도 샤프닝/헤일로/노이즈 중
    어느 것도 "이 값을 새 파라미터로 코드에 반영하자"고 할 만큼
    확실하고 비혼재된 신호가 나오지 않았음. 기존 과적합 방지 원칙에
    따라 `brands/hasselblad.py`에는 변경을 가하지 않기로 결정 — 이번
    분석의 실질적 산출물은 "반영 안 하는 게 맞다"는 근거 있는 결론.
- **재검증(2026-07, brands/core/tools 리팩토링 후)**: `apply_hncs`(순정)와
  `apply_hncs_learned`(런드)를 `tools.calibrate grid_search`/`learn_curve`로
  다시 돌려서 RMSE가 리팩토링 전과 완전히 동일하게 재현됨을 확인
  (23.31→16.51 grid_search, 23.31→15.41 learn_curve) - raw+jpeg 페어가
  여전히 10장뿐이라(나머지는 죽은 링크) 더 재보정할 새 데이터는 없음
- **day/night v3**: 공식 샘플 124장을 콘택트시트로 만들어 한 장씩 육안
  검토, 확실한 야간 장면 12장(가로등/네온/오로라/은하수/도심야경 등)을
  골라내고 나머지 112장을 day로 재분류(v2는 day 5장+night 4장뿐이었음).
  새 타깃: day 블랙p2=11.5/화이트p99.5=224.1(n=112), night 블랙p2=9.7/
  화이트p99.5=221.3(n=12) - v2보다 표본이 훨씬 크고 여전히(오히려 더)
  전체 population 타깃(11.3/223.9)에 수렴함. `apply_hasselblad_day`는
  새 타깃으로 재피팅(midtone_gamma 0.95→0.85, contrast_n 1.15→1.35,
  white_point 0.96→0.92, RMSE 22.01→18.65), `apply_hasselblad_night`는
  그리드서치해도 기존 기본값이 그대로 최적으로 나와 변경 없음. day/night를
  별개 프리셋으로 유지할 근거는 계속 약해지는 중(통합은 아직 안 함)

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
- `apply_hncs_learned` (v12): toe/shoulder 모양을 가정하지 않고
  raw+jpeg 페어에서 neutral_L→target_L 매핑을 픽셀 단위(1,078만 쌍)로
  직접 학습 — RMSE 15.4로 파라메트릭(23.3)보다 더 나음. 다만 raw+jpeg
  페어가 10장뿐이라 표본 수 제약은 동일하게 있고, 8비트 변환 왕복
  과정에서 나오는 hue 오차가 `apply_hncs`보다 약간 큼(평균 |delta|~3.0/179,
  여전히 육안상 무시할 수준)
- 학습 LUT을 표본 부족 우려로 파라메트릭 커브 쪽에 정규화해봤지만, 10장
  leave-one-out 교차검증 결과 정규화 없는 순수 경험적 LUT이 가장 좋음
  (LOO RMSE 14.6, 정규화를 강하게 걸수록 20.7→28.0으로 악화) — bin당
  픽셀 표본이 충분히 많아 분산 문제보다 파라메트릭 커브 자체의 모양
  편향이 더 크기 때문. `apply_hncs_learned`는 정규화 없이 그대로 유지

## 후지필름 (`brands/fuji.py`)

후지는 카메라에 내장된 필름시뮬레이션(Provia/Astia/Velvia/Classic
Chrome/Pro Neg Std 등) 프리셋이 여러 개 있어서, 핫셀블라드와 다른
검증 방법을 씀: mirrorlesscomparison.com 리뷰 갤러리에서 진짜
미편집 SOOC JPEG를 모으고, exiftool로 읽은 실제 Film Mode 태그별로
population 통계를 비교해서 각 프리셋이 실측과 같은 방향으로 채도/톤을
움직이는지 확인 (`tools/analyze.py fuji_film_modes`).

- raw+jpeg 같은 사진 페어를 노려봤지만(`tools/download.py fuji-pairs`),
  이 사이트의 "RAW samples"와 "SOOC JPG samples" 폴더는 애초에 같은
  촬영을 짝지어 올린 게 아니라 그냥 각각 다른 사진들이었음 - 10개
  카메라, RAW 57장+JPEG 40장을 받았는데 EXIF 촬영시각이 정확히 일치하는
  페어는 3쌍뿐(그마저 다 Provia). raw 기반 캘리브레이션(핫셀블라드
  v10~v12급)은 포기하고 population 비교로 전환.
- 실측(n=8~15) vs `apply_astia`/`apply_pro_neg_std`를 Provia 사진에
  적용했을 때의 방향 비교 결과, 둘 다 실측과 정반대로 채도가 올랐음
  (Astia 실측 -12.9 vs 프리셋 +9.4, Pro Neg Std 실측 -19.4 vs 프리셋
  +11.3). 원인은 톤커브를 BGR 채널에 개별로 걸어서 채널 간 격차가
  벌어지며 채도가 재상승하는 것 (원본 125.0 -> HSV desaturation 후
  109.4 -> BGR별 커브 후 139.7, 원본보다도 높아짐). Lab L채널에만
  커브를 적용하도록 두 프리셋 다 수정.
- Pro Neg Std는 L채널로 옮긴 뒤에도 여전히 반대 방향이었는데, 커브
  모양 자체가 틀렸던 것으로 판명 - 기존엔 대비를 강조하는 S커브
  (n=1.4)를 썼는데 실측은 Pro Neg Std가 Provia보다 오히려 대비가 낮은
  플랫한 프로파일(블랙p2 +2.7, 화이트p99.5 -19.0)이었음. 대비 완화
  커브(n=0.65)로 교체.
- 수정 후 재검증: Astia 1/3 → 2/3 방향 일치, Pro Neg Std 0/3 → 3/3
  방향 일치.

## 라이카 (`brands/leica.py`)

라이카는 후지식 다중 필름시뮬레이션이 없고, 핫셀블라드 공식 킷 같은
raw+jpeg 페어 세트도 못 찾음 (dpreview/kenrockwell/photographyblog는
Cloudflare 봇 차단, stevehuffphoto.com은 Photoshop/Lightroom 편집본이라
SOOC 아님, leicarumors.com이 링크한 DNG는 Dropbox 폴더인데 JS
렌더링이라 목록을 못 긁음 - Fuji 때 Google Drive는 `gdown`으로
우회했지만 Dropbox는 동급 도구가 없었음. 라이카 공식 사이트를 Drupal
jsonapi까지 파봤지만 역시 노출 안 됨, imaging-resource.com 갤러리도
M9/X Vario/SL2 외에 추가로 찾은 슬러그가 전부 무효였음). 대신
imaging-resource.com 카메라 리뷰 갤러리에서 미편집 SOOC JPEG 45장
(M9/X Vario/SL2, exiftool Software 태그로 Photoshop/Lightroom 편집본
제외)을 모아 population 통계만 냈음 - 핫셀블라드 v8/v9와 같은 급, raw
대비 진짜 전/후 피팅은 아직 없음.

- population 통계(n=45): 블랙p2=9.2, 화이트p99.5=229.8, 채도=98.6.
  카메라별 편차가 커서(SL2 화이트p99.5=192.1 vs M9 251.6) 표본이 더
  모일 때까지 전체 평균을 타깃으로 사용
- `apply_leica_look()`은 이 population 타깃을 `film_curve`의
  toe_lift/white_point에 직접 대입해서 만든 1차 버전 - raw 기준선이
  없어 그리드서치로 피팅한 게 아니고, shoulder_start/clahe_clip/
  hue·채도 무조작 가정은 전부 핫셀블라드 값을 검증 없이 차용한 것.
  raw 페어를 구하면 제일 먼저 검증해야 할 부분

## Phase One (`brands/phaseone.py`)

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
- `apply_phaseone_look()`도 라이카와 같은 방식(raw 기준선 없이
  population 타깃을 toe_lift/white_point에 직접 대입) - shoulder_start/
  clahe_clip/hue·채도 무조작 가정 미검증인 것도 동일

## Pentax (`brands/pentax.py`)

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

## Ricoh GR (`brands/ricoh_gr.py`)

imaging-resource.com 리뷰 갤러리(GR III + GR IIIx)에서 population 통계
추출. 펜탁스와 같은 리코이미징 브랜드라 EXIF 패턴도 동일.

- 1차 수집(n=40)에서 GR IIIx에 조리개 브라케팅 테스트샷(-f2.8/-f4.0/
  -f8.0 등, 같은 장면 반복 촬영 6장)이 섞여 population을 왜곡 - Phase
  One의 ISO 차트와 같은 종류 문제. 파일명 정규식(`-f\d`)으로 걸러내고
  재계산(영향은 작았음: 채도 87.7→84.9, 표본 비중이 15%로 ISO 테스트
  30%보다 적었기 때문). `tools/analyze.py`의 스킵 패턴에 반영해서 다음
  실행부터는 자동 제외
- population 통계(n=34, f값 테스트 제외): 블랙p2=10.3, 화이트p99.5=243.9,
  채도=84.9
- `apply_ricoh_gr_look()`도 동일한 population-fit 방식, 동일한 미검증
  한계
