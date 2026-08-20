# 브랜드 시그니처 판별기 (연구용 결정력 검증 도구)

## 배경 / 문제

`datasets/<brand>/{tone,color,gamut,texture}_signature.json`은 11개
population-fit 브랜드(hasselblad/canon/leica/nikon/olympus/panasonic/
pentax/phaseone/ricoh_gr/sigma/sony, 총 933장)에 대해 이미 픽셀 단위
톤/채도-hue/텍스처/Lab 색역 통계를 사진 단위로 계산해뒀다(`per_image`
배열). 지금까지는 이 데이터를 population 평균으로만 써서 `brands/*.py`의
`apply_*` 함수 파라미터를 피팅하는 데 썼을 뿐, "이 시그니처들이 브랜드를
실제로 구별할 만큼 결정력이 있는가" 자체는 검증한 적이 없다.

이 스펙은 새 기능이 아니라 **이미 계산된 실측 데이터에 대한 연구용
검증**이다 - `apply_*` 함수들이 근거로 삼는 시그니처 자체가 브랜드마다
통계적으로 유의미하게 다른지, 아니면 노이즈 수준의 차이를 과대해석하고
있는 건 아닌지를 leave-one-out 교차검증으로 정직하게 확인한다. 새 사진을
입력받아 예측하는 기능(실사용 도구)은 이번 스코프에 넣지 않는다 - 목적이
"연구용 결정력 검증"이라는 걸 명확히 하기 위해 의도적으로 제외한다.

## 목표

1. 11개 브랜드의 4종 시그니처 `per_image` 데이터만으로 leave-one-out
   교차검증 기반 nearest-centroid 분류기를 구현한다.
2. 피처셋을 두 가지로 나눠(texture 포함/제외) 각각 confusion matrix와
   정확도를 산출하고 비교한다 - texture의 sharpening/micro_contrast는
   브랜드마다 계산 공식이 달라서(Canon/Sony vs Nikon/Leica/Pentax/
   Ricoh GR 스케일 다름, `docs/project_structure.md` 기존 문서화) 판별기가
   "색감 차이"가 아니라 "계산 공식 차이"를 맞출 위험이 있다는 걸 실측으로
   직접 확인한다.
3. 결과(다수결/균등확률 baseline 대비 개선 여부, 브랜드별 precision/
   recall, 표본이 얇은 브랜드의 신뢰도 한계)를 정직하게 문서화한다 -
   판별력이 낮게 나와도 그 자체가 유효한 연구 결과다.

## 범위 밖

- 임의의 새 사진을 입력받아 브랜드를 예측하는 기능 (시그니처 계산
  파이프라인을 단일 이미지용으로 재구성해야 해서 별도 스펙 필요 - 이번엔
  이미 계산된 933장 데이터만 사용)
- Fuji 필름 시뮬레이션(`datasets/fuji/`) - 데이터 구조가 population
  signature 4종과 달라서(차트 비교 기반) 이번 스코프에서 제외
- kNN/sklearn 등 새 의존성 도입 (표준화 거리 nearest-centroid로 충분,
  프로젝트의 numpy-only 핵심 모듈 원칙 유지)
- `brands/*.py`의 `apply_*` 파라미터 재조정 - 이 스펙은 순수 검증이고,
  결과가 어떻게 나오든 기존 브랜드 함수를 바꾸지 않는다

## 설계

### 1. 데이터 로딩 및 조인

각 브랜드 디렉토리에서 4개 JSON(`tone_signature.json`,
`color_signature.json`, `gamut_signature.json`, `texture_signature.json`)의
`per_image` 리스트를 `filename` 키로 inner join한다. 네 파일의 파일셋이
정확히 일치하지 않을 가능성에 대비해, 조인 후 브랜드별 최종 샘플 수를
원본 `n_images`와 비교해서 불일치가 있으면 경고 로그를 남긴다(이 프로젝트가
반복적으로 겪은 "파일명 매칭 불확실" 부류 문제에 대한 방어적 습관,
`datasets/hasselblad/texture_signature_recomputed.json`의 선례를 따름).

### 2. 피처 추출

**Set A (tone+color+gamut, 14차원, 기본값)**:
- tone: `b2`, `w995`, `median`, `dark_pct`
- color: `sat_mean`, `hue_mean`(원형 변수 - 아래 참고), `skin_hue`는
  결측이 많아(비portrait 사진엔 없음) 제외
- gamut: `a_p1`, `a_p99`, `b_p1`, `b_p99`, `a_std`, `b_std`, `chroma_mean`,
  `chroma_p99`

**Set B (Set A + texture, 20차원)**: `sharpening`, `micro_contrast`,
`noise`, `n_edges`, `overshoot`, `undershoot` 추가.

**명시적으로 제외하는 필드**: `npix`, `is_portrait`, `quality`,
`subsampling`. 이것들은 색감이 아니라 이미지 크기/JPEG 인코더 설정이라,
포함시키면 분류기가 "브랜드의 색 렌더링"이 아니라 "어느 브랜드가 어떤
해상도/JPEG 품질로 갤러리에 올렸는지"라는 무관한 지름길을 학습해버린다 -
이 프로젝트의 "판별력의 근거가 실제로 무엇인지 정직하게 밝힌다"는 원칙에
위배되므로 처음부터 제외.

**원형 hue 처리**: `hue_mean`은 0~360도 순환값이라 raw 값에 z-score를
그대로 적용하면 359도와 1도가 실제로는 가까운데도 거리 계산에서 최대로
멀게 취급된다. `(cos(hue), sin(hue))` 2차원으로 변환해서 이 문제를
피한다 - Set A는 이 변환으로 실질 15차원, Set B는 21차원이 된다.

### 3. 표준화 거리 nearest-centroid 분류

매 leave-one-out 폴드(held-out 이미지 i, 실제 브랜드 B_true)마다:

1. i를 전체 풀에서 제외한 나머지로 피처별 **글로벌**(전 브랜드 통합) 평균/
   표준편차를 계산해서 표준화 기준으로 쓴다 - 브랜드별 표준편차를 따로
   쓰는 Mahalanobis 방식은 `phaseone`(n=16)처럼 얇은 표본에 15~21차원을
   맞추면 그 자체가 불안정해지므로 채택하지 않음(설계 논의에서 확정).
2. 같은 기준으로 i를 표준화하고, 각 브랜드(자기 브랜드는 i 제외한
   나머지로) centroid(평균 벡터)와의 유클리드 거리를 계산.
3. 거리가 가장 가까운 브랜드를 예측값으로 함.

933장 전체에 대해 이 폴드를 반복해서 11×11 confusion matrix를 만든다.

### 4. 평가 지표

- 11×11 confusion matrix (Set A/B 각각)
- 브랜드별 precision/recall/F1, 표본 수(n) 같이 표기
- macro-averaged accuracy
- 비교 기준선: 다수결 baseline(가장 큰 브랜드의 비율, ≈13.3%), 균등확률
  baseline(1/11 ≈ 9.1%)
- **얇은 표본 경고**: leica(45)/pentax(40)/phaseone(16)은 recall이 fold
  수가 적어 노이즈가 클 수 있다는 걸 출력에 표본 수와 함께 명시

### 5. 코드 구조

- `core/brand_classifier.py`: `load_signatures(brand)`(조인),
  `extract_features(records, feature_set)`(Set A/B + 원형 hue 변환),
  `standardize(train_pool, test_vector)`, `nearest_centroid_loo(all_brands,
  feature_set)`(전체 LOO 루프, confusion matrix 반환) - numpy만 사용,
  기존 `core/stats.py`/`core/validation.py`와 같은 스타일(순수 함수,
  부작용 없음).
- `tools/classify_brand.py`: CLI. `python3 -m tools.classify_brand
  --features tone_color_gamut` (Set A, 기본값) 또는 `--features all`
  (Set B) - confusion matrix + 지표를 콘솔에 표로 출력. `--csv PATH`로
  confusion matrix를 파일로도 저장 가능(선택적 플래그).

### 6. 문서화

README.md/README.ko.md에 짧은 절 추가(다른 실험적/연구용 도구, 예:
`tools/highlight_rolloff_signal.py`와 비슷한 톤 - "이런 걸 해봤고 결과는
이렇다"). Set A/B confusion matrix 핵심 수치와 얇은 표본 브랜드에 대한
해석 주의사항 포함. `docs/project_structure.md`/`.en.md`에 두 파일 행 추가.

## 테스트 계획

`tests/test_brand_classifier.py`, 합성 데이터 기반(933장 실데이터로
자동테스트 시간 낭비 안 함):

- **LOO 리키지 방지 검증(가장 중요)**: held-out 샘플의 피처 값을 극단적으로
  바꿔도(예: 다른 모든 값보다 훨씬 큰 값) 자기 브랜드의 centroid가 변하지
  않는지 직접 확인 - "self-exclusion이 실제로 작동하는가"를 회귀로 고정.
- 완전히 분리된 합성 클러스터(브랜드 3개, 각 20샘플, 클러스터 중심이
  충분히 떨어짐) 넣었을 때 LOO 정확도가 100%에 가깝게 나오는지(분류기
  로직 자체의 정상 동작 확인).
- 원형 hue 변환: hue=359와 hue=1이 표준화 공간에서 hue=180보다 훨씬
  가깝게 나오는지 직접 검증(랩어라운드 버그 회귀 테스트).
- `npix`/`is_portrait`/`quality`/`subsampling`이 피처 추출 결과에 전혀
  포함되지 않는지 확인(제외 목록이 실수로 깨지는 걸 방지).
- 4개 시그니처 파일의 파일셋이 불일치하는 합성 케이스에서 조인이 올바르게
  경고를 내고 교집합만 쓰는지 확인.
- `python3 -m tools.classify_brand`가 실제 `datasets/`로 end-to-end 실행돼
  에러 없이 confusion matrix를 출력하는지는 수동 스모크테스트로 확인
  (다른 `tools/*.py` CLI들과 동일한 관례 - 실데이터 기반 실행은 자동화된
  unit test 범위 밖).

## 한계 / 이 스펙이 답하지 않는 것

- **인과관계 아님**: 판별이 잘 되더라도 "왜" 되는지(정말 카메라 색과학
  차이인지, 사진작가/장르/피사체 선택 편향인지)는 이 검증이 답할 수 없다 -
  population 자체가 갤러리 큐레이션이라는 기존 한계(`docs/methodology.md`)
  그대로 이어받음.
- **표본 불균형**: 933장 중 phaseone 16장, pentax 40장, leica 45장인 반면
  hasselblad/olympus/panasonic/canon/sony는 100장 이상 - macro accuracy와
  다수결 baseline을 같이 보여주는 것으로 완화하지만 근본적으로 해소되진
  않음.
- 판별이 잘 안 되는 결과가 나와도(가능성 있음) `apply_*` 함수를 재조정하지
  않는다 - 그건 별도 스펙의 몫이며, 이 검증의 목적이 애초에 아니다.
