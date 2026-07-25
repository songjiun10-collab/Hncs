# "재미용" 브랜드 예측기 - predict-from-new-photo

## 배경 / 문제

`core/brand_classifier.py`/`tools/classify_brand.py`(2026-07-24 스펙/구현)는
연구용 검증 도구로, 이미 계산된 852장(10개 브랜드)의 population 시그니처
데이터만 갖고 leave-one-out 교차검증으로 "이 데이터가 브랜드를 구별할
결정력이 있는가"를 확인했다. 그 스펙의 "범위 밖" 섹션에서 명시적으로
제외했던 게 "임의의 새 사진을 입력받아 브랜드를 예측하는 기능"이다 -
시그니처 계산 파이프라인을 단일 이미지용으로 재구성해야 해서 별도
스펙이 필요하다고 남겨뒀었다.

이 스펙이 그 후속이다. 목적은 연구가 아니라 **재미** - 사용자가 아무
사진이나 넣으면 "이 사진이 어느 브랜드 색감과 가장 비슷한가"를 보여주는
도구. 다만 재미용이라고 해서 근거 없는 숫자를 만들면 안 된다는 이
프로젝트의 원칙은 그대로 유지한다 - 실제 판별 정확도가 19.6%(Set A,
다수결 baseline 14.6%)라는 걸 이미 알고 있으므로, 순위는 보여주되
가짜 확신을 주는 표현(예: "87% 확률로 Sony")은 금지한다.

## 목표

1. 임의의 사진 파일(사용자가 갖고 있는 아무 JPEG)에서 브랜드 시그니처와
   같은 형식의 피처 벡터(tone/color/gamut, Set A 15차원)를 계산한다.
2. 그 피처 벡터를 852장 전체(10개 브랜드) 훈련 풀 기준으로 표준화하고,
   10개 브랜드 centroid까지의 거리를 오름차순으로 순위 매긴다.
3. CLI 서브커맨드로 노출하고, 선택적으로 자기완결적(사진 base64 내장)
   정적 HTML 리포트를 생성한다.
4. 정확도 한계(19.6%)를 결과물에 항상 명시해서 과대해석을 막는다.

## 범위 밖

- **texture 피처는 이번 기능에서 아예 안 씀.** `datasets/*/texture_signature.json`의
  sharpening/micro_contrast 계산 스크립트가 브랜드마다 원본이 커밋에
  안 남아있어(기존 문서화된 문제, `docs/project_structure.md` 참고),
  새 사진에 대해 "그 브랜드가 쓴 것과 동일한 공식"을 재현할 방법이
  없다. Set A(tone+color+gamut)만 지원.
- 브라우저에서 완전히 동작하는 클라이언트사이드(JS) 버전 - OpenCV의
  HSV/Lab 변환·percentile 계산을 canvas로 재현하면 미묘하게 어긋날
  위험이 있고(이 프로젝트가 ricoh_gr 사례로 이미 "계산 공식 불일치"
  문제를 겪었다), Python 단일 소스를 유지하는 쪽이 안전하다.
- 이미 승인/테스트 완료된 `nearest_centroid_loo()`/`confusion_matrix()`/
  `classification_report()`는 수정하지 않는다 - 새 함수만 추가.
- 서버/웹 호스팅 - CLI로 로컬에서 HTML을 "생성"하는 것까지만. 상시
  띄워두는 웹 서비스는 스코프 밖.
- 원본 852장 시그니처 데이터 자체의 재계산/검증 - 그건 이미 존재하는
  데이터를 그대로 신뢰하고 쓴다.

## 설계

### 1. `core/photo_signature.py` (신규)

임의의 BGR uint8 이미지에서 시그니처 JSON들의 `per_image` 레코드와
같은 필드 이름으로 tone/color/gamut 값을 계산한다. 각 시그니처 JSON의
`methodology` 필드에 문서화된 공식을 그대로 재구현:

```python
def compute_signature(img_bgr):
    """img_bgr(BGR uint8)에서 tone/color/gamut 시그니처 필드를 계산.
    texture는 계산 안 함(브랜드별 원본 공식 유실 - 모듈 docstring 참고).
    tone_signature.json/color_signature.json/gamut_signature.json의
    methodology 필드에 문서화된 정의를 그대로 재구현한 것으로,
    원본 계산 스크립트를 복원한 게 아니라 근사 재구현이다."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

    # tone: b2/w995/median/dark_pct (tone_signature.json methodology)
    b2 = float(np.percentile(gray, 2))
    w995 = float(np.percentile(gray, 99.5))
    median = float(np.median(gray))
    dark_pct = float((gray < 40).sum() / gray.size * 100)

    # color: sat_mean/hue_mean, S>20 마스크 (color_signature.json methodology)
    s = hsv[:, :, 1].astype(np.float64)
    h = hsv[:, :, 0].astype(np.float64)
    mask = s > 20
    sat_mean = float(s[mask].mean()) if mask.any() else 0.0
    # hue_mean: OpenCV H는 0~179(=0~358도)를 원형으로 평균해야 함 -
    # 원형 평균(circular mean)으로 계산, 단순 산술평균 아님
    if mask.any():
        h_rad = np.deg2rad(h[mask] * 2.0)  # OpenCV 0-179 -> 0-358도
        hue_mean = float(np.degrees(np.arctan2(np.sin(h_rad).mean(), np.cos(h_rad).mean())) % 360)
    else:
        hue_mean = 0.0

    # gamut: Lab a/b (OpenCV 8bit, 128=무채색 중심), gamut_signature.json methodology
    a = lab[:, :, 1].astype(np.float64)
    b = lab[:, :, 2].astype(np.float64)
    chroma = np.sqrt((a - 128.0) ** 2 + (b - 128.0) ** 2)

    return {
        "b2": b2, "w995": w995, "median": median, "dark_pct": dark_pct,
        "sat_mean": sat_mean, "hue_mean": hue_mean,
        "a_p1": float(np.percentile(a, 1)), "a_p99": float(np.percentile(a, 99)),
        "b_p1": float(np.percentile(b, 1)), "b_p99": float(np.percentile(b, 99)),
        "a_std": float(a.std()), "b_std": float(b.std()),
        "chroma_mean": float(chroma.mean()), "chroma_p99": float(np.percentile(chroma, 99)),
    }
```

반환된 dict는 `core.brand_classifier.extract_features([이 dict],
feature_set="tone_color_gamut")`에 그대로 넣을 수 있는 형태(필요한
필드를 전부 포함) - 기존 피처 추출 로직을 재사용하고 중복 안 만듦.

**주의**: `hue_mean`의 원형 평균 처리는 원본 시그니처 계산 스크립트가
정확히 이렇게 했는지 확인할 방법이 없다(스크립트 유실). 산술평균과
원형평균은 hue 분포가 0도 근처에 몰려있지 않은 한 큰 차이가 안
나지만, 완전히 같다는 보장은 없다는 걸 모듈 docstring에 명시.

### 2. `core/brand_classifier.py`에 함수 추가

```python
def rank_brands_by_distance(query_vector, train_X, train_y):
    """query_vector(D,)가 train_X/train_y(전체 훈련 풀, held-out 없음)
    기준으로 각 브랜드 centroid와 표준화 공간에서 얼마나 가까운지
    오름차순으로 정렬해서 반환. nearest_centroid_loo()와 달리 폴드마다
    제외할 대상이 없다 - query_vector는 애초에 train_X에 속하지 않는
    새로운 사진이라 리키지 문제 자체가 없음."""
    z = standardize(train_X, query_vector)
    ranking = []
    for brand in np.unique(train_y):
        centroid_raw = train_X[train_y == brand].mean(axis=0)
        centroid_z = standardize(train_X, centroid_raw)
        dist = float(np.linalg.norm(z - centroid_z))
        ranking.append((brand, dist))
    ranking.sort(key=lambda pair: pair[1])
    return ranking
```

`standardize()`(이미 테스트/승인됨)를 그대로 재사용. `nearest_centroid_loo()`는
전혀 수정하지 않음 - 별도 함수로 추가만 함.

### 3. `tools/classify_brand.py`에 `predict` 서브커맨드 추가

```
python3 -m tools.classify_brand predict photo.jpg
python3 -m tools.classify_brand predict photo.jpg --html result.html
```

동작:
1. `cv2.imread(photo.jpg)`로 로드.
2. `core.photo_signature.compute_signature()`로 피처 계산.
3. `core.brand_classifier.extract_features([그 dict], feature_set="tone_color_gamut")`로
   벡터화(기존 로직 재사용).
4. 852장(10개 브랜드) 전체를 `load_signatures`+`extract_features`로
   로드(기존 `run()`의 로딩 부분과 동일 - 공유 헬퍼로 추출해서 중복
   제거).
5. `rank_brands_by_distance()`로 순위 계산.
6. 콘솔 출력: 1위 브랜드 + 10개 전체 순위(거리), 그리고 **"참고: 이
   판별기의 실측 정확도는 19.6%(다수결 baseline 14.6%) - 순위는
   참고용이지 확정적 판정이 아님"** 경고 줄을 항상 출력.
7. `--html PATH`가 있으면 정적 HTML 파일 생성:
   - 입력 사진을 base64 data URI로 내장(자기완결적 - 파일 하나만
     공유해도 열림)
   - 1위 브랜드 + 순위표(브랜드/거리)
   - 6번의 정확도 경고 배너를 페이지 상단에 고정 표시
   - 외부 CDN/폰트 의존 없음(오프라인에서도 열림)

### 4. 문서화

README.md/README.ko.md의 "브랜드 시그니처 판별력 검증 (연구용)" 절
바로 아래에 짧은 하위 절 추가 - "그리고 재미로" 톤으로, `predict`
서브커맨드 사용법과 정확도 한계를 한 번 더 명시. `docs/project_structure.md`/`.en.md`에
`core/photo_signature.py` 행 추가.

## 테스트 계획

`tests/test_photo_signature.py` (신규, unittest 스타일, 합성 이미지만
사용):
- 균일한 회색(128,128,128) 이미지 → `sat_mean`이 0에 가까움(무채색이라
  S 채널이 낮음), tone 필드들(b2/w995/median)이 전부 그 그레이값
  근처.
- 순수 빨강 패치(BGR (0,0,255)) → `hue_mean`이 OpenCV 빨강 hue(0도
  근처)에 가까움, `sat_mean`이 높음, `chroma_mean`이 무채색(0)보다
  뚜렷이 큼.
- 두 색이 절반씩인 이미지에서 `hue_mean`의 원형평균이 산술평균과
  달라지는 경우(0도 근처와 359도 근처 색을 섞음) - 원형평균이 올바르게
  두 색 "사이"(0도 근처)를 가리키는지, 산술평균이라면 180도 근처로
  잘못 나올 것을 대조 확인.
- 반환된 dict가 `extract_features()`에 바로 들어가서 에러 없이
  15차원 벡터가 나오는지(통합 확인, 필드명 불일치 회귀 방지).

`tests/test_brand_classifier.py`에 `rank_brands_by_distance` 테스트
추가 - 이미 만들어둔 합성 클러스터(3브랜드, well-separated)에 새
쿼리 포인트를 하나 추가해서 가장 가까운 브랜드가 1위로 나오는지,
순위가 오름차순인지 확인.

`predict` 서브커맨드는 `docs/images/`에 있는 실제 데모 사진(예:
`before_after_hncs.jpg`)으로 수동 스모크테스트 - 콘솔 출력과 `--html`
결과물이 에러 없이 생성되는지 확인(다른 `tools/*.py`와 동일한 관례,
자동화 테스트 범위 밖).

## 한계 / 정직하게 명시할 것

- `compute_signature()`는 원본 계산 스크립트의 복원이 아니라 methodology
  필드 설명 기반의 재구현 - 특히 `hue_mean`의 원형평균 처리는 원본과
  100% 동일하다는 보장이 없음(모듈 docstring에 명시).
- 이 기능은 애초에 정확도 19.6%짜리 도구 위에 얹은 것 - "예측"이라는
  말이 주는 확신을 결과물(콘솔+HTML) 양쪽에서 계속 깎아내려야 함.
  가짜 확률/퍼센트를 절대 표시하지 않는다(순위와 거리만).
- texture를 뺐기 때문에, 연구용 도구의 Set B(49.8%)보다 이 기능의
  체감 "적중률"은 낮게 느껴질 수 있음 - 의도된 트레이드오프임을
  문서에 남김.
