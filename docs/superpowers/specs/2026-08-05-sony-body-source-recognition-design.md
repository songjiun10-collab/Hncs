# Sony 바디별 소스 인식 (hybrid_engine.convert) - 파일럿 (설계)

## 배경

`hybrid_engine.convert`(다른 카메라로 찍은 JPEG를 이 프로젝트가 지원하는
브랜드 룩으로 다시 렌더링하는 CLI)는 EXIF Make/Model로 소스 브랜드를
인식해 `remove_camera_signature()`로 그 브랜드의 필름커브를 역산한
뒤(`hybrid_engine/core/preset_inverse.py`), 타깃 브랜드의 실제 `apply_*`
함수를 재적용한다. 이 역산은 `curve_params(brand)`가 반환하는
`toe_lift`/`shoulder_start`/`white_point` 세 값에 의존하는데, 지금은
**브랜드 하나당 값 하나**(pooled, `BRAND_FUNCS[brand]`의 함수 기본값)뿐이다
- 소니 A7로 찍었든 A7 IV로 찍었든 똑같은 "sony" 커브를 역산에 쓴다.

`brands/sony.py`를 읽어보면 population-fit 브랜드의 `toe_lift`/
`white_point`는 그리드서치가 아니라 **population 통계를 255로 나눈 값을
그대로 대입**한 것뿐이다(`_TOE_LIFT = 9.1/255`, `_WHITE_POINT = 228.6/255`,
`brands/sony.py:94-95`). `shoulder_start`/`clahe_clip`은 애초에 브랜드별로
피팅할 근거가 없어 핫셀블라드 값을 전부 차용 중이고(`core/engine.py`
docstring), 이건 바디 단위로 내려가도 마찬가지로 못 구한다. 즉 바디별로
새로 만들 수 있는 값은 **`toe_lift`/`white_point` 두 개뿐**이고, 이미
가진 population 데이터에서 바로 계산 가능하다(새 촬영/새 스크레이핑 불필요).

`brands/sony.py`는 이미 바디별 population 수치를 기록해뒀다(n=115,
바디당 23장):

```
A7    (2013,n=23):   블랙p2=9.7   화이트p99.5=243.5
A7R   (2013,n=23):   블랙p2=7.7   화이트p99.5=232.3
A7S   (2014,n=23):   블랙p2=8.9   화이트p99.5=245.5
A7 III(2018,n=23):   블랙p2=10.7  화이트p99.5=185.3
A7 IV (2021,n=23):   블랙p2=8.9   화이트p99.5=236.5
```

**알려진 한계(문서화됨, 무시하지 않고 검증 설계에 반영)**: A7 III의
화이트p99.5(185.3)가 나머지(232~245)보다 눈에 띄게 낮은데, 같은
docstring이 이미 "105mm/28-200mm 렌즈 테스트용 실내 저대비 피사체 위주
표본이라 카메라 자체 렌더링 차이인지 촬영 세트 편향인지 원인 미확인"이라고
못박아뒀다. 이 파일럿의 검증(held-out LOO)이 이 편향을 실제로 걸러내는지
자체가 이 실험의 일부다 - A7 III만 유의미한 개선이 안 나오는 결과도
"성공"으로 취급한다(편향을 편향으로 정확히 판정한 것이므로).

## 조사한 것 (실측)

- `sony_stats_result.csv`(이 컨테이너에 이미 존재, **git-ignored** -
  `.gitignore`의 `*_stats_result.csv` 패턴)에 115장 전부의 개별
  `camera,filename,url,b2,w995,med,sat,dark_pct`가 그대로 남아있다.
  `camera` 컬럼값은 `Sony A7`/`Sony A7R`/`Sony A7S`/`Sony A7 III`/
  `Sony A7 IV` 5종, 각 23장씩(직접 `cut -d, -f1 | uniq -c`로 확인).
  **이 평가는 이미지 재디코드 없이 이 CSV만으로 가능**(각 행이 이미
  `core/stats.py`의 `image_stats()` 결과 그대로).
- `downloaded_samples_sony/`(115장, git-ignored)도 이 컨테이너에 남아있어
  CSV가 유실되면 `core/stats.py:image_stats()`로 재계산 가능하지만,
  **원본 스크레이핑 스크립트는 커밋된 적이 없다**(`brands/sony.py`
  docstring: "Canon/Nikon 작업과의 동시편집 충돌을 피하려고 별도
  스크립트로 수집" - 그 스크립트 자체는 저장 안 됨, `tools/analyze.py`의
  `BRAND_CONFIGS`에도 sony는 없음). 두 캐시 모두 사라지면 imaging-resource.com
  갤러리를 처음부터 다시 긁어야 한다 - 이 스펙의 범위 밖.
- `hybrid_engine/core/preset_inverse.py`의 `curve_params(brand)`(:73)는
  `BRAND_FUNCS[brand]`의 함수 시그니처 기본값을 `inspect.signature`로
  읽어온다 - `brands/sony.py`를 건드리지 않고 이 함수만 확장하면 됨.
- `detect_brand_from_exif(make, model)`(:119)는 이미 `model` 문자열을
  받고 있다(Pentax/Ricoh GR 구분용) - 바디 인식에 같은 인자를 재사용
  가능, 시그니처 변경 불필요.

## 검증 설계

**LOO 예측오차 비교** - 115장 전부에 대해 한 장씩 held-out:

- 바디별 예측: held-out 사진과 같은 바디의 나머지 22장 평균 b2/w995
- pooled 예측(기존): held-out 사진을 포함한 전체 115장 중 나머지 114장
  평균 b2/w995 (브랜드 전체 pooled 값과 동일한 방식)
- 각 방식의 오차 = `|held-out 사진의 실제 b2 - 예측값|` (b2/w995
  따로 계산, 총 115쌍의 페어드 비교 x 2통계)

**판정**: `hybrid_engine/CLAUDE.md`의 4종 검정 그대로(부호검정 + 부트스트랩
95% CI 20000회 + drop-one 민감도) - `tools/evaluate_hncs_blend.py`의
`summarize()`를 복사해서 재사용(brand-agnostic, ΔE 전용 코드 없음 -
b2/w995 오차값 리스트만 받으면 그대로 동작).

**바디별 개별 판정** - 전체 115장을 합쳐서 한 번에 검정하지 않고,
5바디 각각 자기 바디의 23쌍만 따로 검정한다(A7 III만 편향으로
드러나도 나머지 4바디는 채택할 수 있어야 하므로). b2/w995 둘 다
CI가 0을 포함하지 않아야 그 바디를 채택.

## 구현 설계

`brands/sony.py`/`apply_sony_look()`는 전혀 안 건드림(정방향 렌더링은
그대로). 변경은 전부 `hybrid_engine/core/preset_inverse.py`에 추가:

EXIF `Model` 태그는 실제로 다운로드된 115장에서 직접 확인함(내부
코드명, 소비자용 이름과 다름) - `ILCE-7`(A7) / `ILCE-7R`(A7R) /
`ILCE-7S`(A7S) / `ILCE-7M3`(A7 III) / `ILCE-7M4`(A7 IV). **부분
문자열 매칭은 못 쓴다** - `"ILCE-7"`가 `"ILCE-7R"`/`"ILCE-7S"`/
`"ILCE-7M3"`/`"ILCE-7M4"` 전부의 접두사라, `in` 체크로는 A7이 항상
먼저 매치돼버린다. 코드명 -> 바디 키 정확매치 딕셔너리로 구현:

```python
SONY_MODEL_CODES = {
    "ILCE-7": "A7", "ILCE-7R": "A7R", "ILCE-7S": "A7S",
    "ILCE-7M3": "A7 III", "ILCE-7M4": "A7 IV",
}

# population 통계 재계산 없이, 위 검증에서 "채택"된 바디만 채운다
# (전부 채택 안 될 수도 있음 - 그러면 이 dict는 비워둔 채로 병합).
SONY_BODY_PARAMS = {
    "A7 III": {"toe_lift": 10.7 / 255, "white_point": 185.3 / 255},
    # ...검증 통과한 바디만
}


def detect_body_from_exif(brand, model):
    """brand가 바디별 데이터를 가진 브랜드고 model이 알려진 코드명과
    정확히 일치하면 바디 키를 반환, 아니면 None(호출부는 pooled로
    폴백). 부분 문자열 매칭 금지(위 설명 참고)."""
    if brand == "sony":
        return SONY_MODEL_CODES.get((model or "").strip())
    return None


def curve_params(brand, body=None):
    """body가 주어지고 그 바디의 전용 데이터가 있으면 그걸 쓰고,
    아니면 기존과 동일하게 브랜드 pooled 기본값."""
    if body and brand in _BODY_PARAMS_BY_BRAND and body in _BODY_PARAMS_BY_BRAND[brand]:
        override = _BODY_PARAMS_BY_BRAND[brand][body]
        base = _pooled_curve_params(brand)  # 기존 curve_params 로직
        base.update(override)
        return base
    return _pooled_curve_params(brand)
```

`remove_camera_signature(img_bgr, brand, body=None)`과
`convert_between_brands(...)`도 `body` 키워드 인자를 추가(기본값 `None`
- 기존 호출부는 전부 그대로 동작, 하위호환). `hybrid_engine/convert.py`
CLI는 새 필수 인자 없이, `--source`가 자동인식이든 수동 지정이든
Model 문자열이 있으면 `detect_body_from_exif`를 추가로 호출해서 body를
채운다(EXIF에 Model이 없거나 안 맞으면 `body=None` -> 지금과 동일한
pooled 동작).

## 채택 기준

바디별로 개별 판정, 전부 통과해야 하는 게 아님:
- b2 오차, w995 오차 **둘 다** CI가 0을 포함하지 않아야 그 바디를
  `SONY_BODY_PARAMS`에 넣는다.
- A7 III가 기각되면(예상되는 결과) - "표본 편향으로 판정, 채택 안 함"을
  결과 그대로 `hybrid_engine/EVALUATION.md`에 기록한다. 실패도 자산.
- 전부 기각되면 이 파일럿은 "판정 보류"로 종료, `preset_inverse.py`는
  변경하지 않는다(구현 설계는 헛일이 아니라 다음에 다른 브랜드로
  재시도할 때 그대로 재사용).

## 기록 위치

`hybrid_engine/EVALUATION.md`에 새 절 추가 - 바디별 b2/w995 LOO 오차
표, 5바디 개별 판정, A7 III 편향 가설이 실제로 확인됐는지 여부.

## 테스트

- `TestSummarizeRecordedRun` 패턴(`hybrid_engine/CLAUDE.md`) - 실제
  LOO 실행 결과의 페어드 오차 표를 하드코딩해서 `summarize()`에
  다시 먹여 문서화된 숫자를 재현하는 회귀 테스트.
- `curve_params(brand, body=None)`/`detect_body_from_exif()`는 이미지
  디코드가 없는 순수 함수라 목킹 없이 직접 유닛테스트 가능:
  `detect_body_from_exif("sony", "ILCE-7M3")` == `"A7 III"`,
  `detect_body_from_exif("sony", "ILCE-7")` == `"A7"`(접두사 오매칭
  없는지 확인하는 회귀 테스트로 명시), `detect_body_from_exif("sony",
  "ILCE-9")` == `None`(모르는 바디는 폴백).

