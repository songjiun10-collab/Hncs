# Fuji X-Trans 데모자이크 알고리즘 비교 실험 (설계)

## 배경

`brands/fuji.py`는 raw+jpeg 페어 캘리브레이션(핫셀블라드 v8~v12급 방식)을
시도했다가 포기한 이력이 있다 - 표본 사이트(mirrorlesscomparison.com)에서
받은 RAW 57장 + JPEG 40장 중 EXIF 촬영시각이 정확히 일치하는 페어는 3쌍뿐
(그마저 전부 Provia/Standard 필름모드)이라 raw 기반 캘리브레이션은 접고
population 비교(서로 다른 사진들을 필름모드별로 모아 통계 비교)로 전환했다.

이번 요청은 그 raw 기반 경로를 되살리는 게 아니라 더 좁다: **rawpy(LibRaw
래퍼)의 기본 데모자이크 알고리즘이 Fuji의 X-Trans 센서에 최적이 아닐 수
있다는 가설을 검증**하는 것. X-Trans는 베이어와 컬러 필터 배열이 달라
(6x6 유사랜덤 패턴 vs 2x2 반복) 범용 데모자이크 알고리즘이 "메이즈"
아티팩트를 만들기 쉽다고 알려져 있고, 데모자이크 단계의 색 오차는
그 이후 어떤 매트릭스/커브 피팅으로도 못 되돌린다 - 그래서 raw 기반
캘리브레이션을 다시 시도하기 전에 데모자이크 자체부터 점검하자는 취지.

## 조사한 것

- `rawpy.DemosaicAlgorithm`에 `AMAZE`(RawTherapee가 쓰는 그 알고리즘)가
  있지만, 이 환경의 LibRaw 빌드는 GPL3 라이선스 팩이 없어 런타임에
  `Demosaic algorithm AMAZE requires GPL3 demosaic pack`으로 실패함(실측
  확인, `raw_calib_cache/x1d-xcd45-01.jpg.3FR`로 테스트).
- `DHT`는 같은 빌드에서 정상 동작함(실측 확인). 특허프리이며 X-Trans의
  메이즈 아티팩트를 줄이는 대안으로 커뮤니티에서 종종 언급되는 알고리즘.
- 대안으로 darktable-cli(Markesteijn 데모자이크, X-Trans 전용 설계)나
  RawTherapee-cli(AMaZE)를 새로 설치하는 방법도 있지만 각각 apt로
  180개+ 패키지(GUI 스택 포함)를 새로 끌어와야 하고, subprocess +
  설정파일(XMP/.pp3) 관리라는 새 복잡도가 생기고, 버전이 바뀌면 이
  프로젝트가 중시하는 재현성(population 통계 재현성 감사)에 리스크가
  생긴다. **이번 실험은 새 프로그램 없이 rawpy 안에서 가능한 DHT부터
  먼저 확인하고, 결과가 유의미하면 그때 darktable 도입을 별도로
  검토한다** - 이 스펙의 범위 밖.
- 로컬에 실제 Fuji raw+jpeg 페어가 이미 존재한다(`fuji_pairs_manifest.csv`,
  3쌍, 전부 F0/Standard(Provia)):

  | camera | raw | jpeg |
  |---|---|---|
  | Fujifilm X-T3 | `raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF` | `.../jpeg/DSCF3954.jpg` |
  | Fujifilm X-T30 | `raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7094.RAF` | `.../jpeg/DSCF7182.JPG` |
  | Fujifilm X-T30 | `raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF` | `.../jpeg/DSCF7030.JPG` |

  (`raw_calib_cache_fuji/`는 `.gitignore`에 있어 커밋되지 않지만 이
  컨테이너 로컬 디스크에 이미 존재 - HNCS 구조 실험 때 쓴
  `raw_calib_cache/`와 같은 패턴.)

## 표본 크기에 대한 솔직한 전제

**3쌍으로는 통계적으로 결론을 낼 수 없다.** 바로 직전에 끝낸 HNCS 구조
실험에서 n=13조차 paired t-test/부호검정/부트스트랩 전부 유의성이
없었다(`hybrid_engine/EVALUATION.md`의 "HNCS 구조 실험" 절 참고). n=3은
그보다도 훨씬 약하다. 이 실험은 "DHT가 확실히 낫다"를 증명하는 게
목적이 아니라 **방향이 일관되게 나오는지(3/3 모두 개선 또는 3/3 모두
악화 같은 극단적 신호가 있는지) 확인하는 예비 점검**이다 - 애매하면
"판단 불가, 더 큰 표본 필요"라고 정직하게 기록하고 끝낸다.

## 설계

### 1. `hybrid_engine/utils/io.py`: `decode_raw()`에 옵션 파라미터 추가

```python
def decode_raw(raw_path, demosaic_algorithm=None):
    """... (기존 docstring 유지, demosaic_algorithm 설명 한 줄 추가) ...
    demosaic_algorithm: None이면 기존과 동일하게 rawpy 기본값을 씀(모든
    기존 호출부 100% 동일 동작 보장). rawpy.DemosaicAlgorithm 값을 넘기면
    raw.postprocess()에 그대로 전달."""
    kwargs = dict(
        use_camera_wb=True,
        no_auto_bright=True,
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        gamma=(1, 1),
    )
    if demosaic_algorithm is not None:
        kwargs["demosaic_algorithm"] = demosaic_algorithm
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(**kwargs)
    return rgb16.astype(np.float64) / 65535.0
```

`decode_raw_native()`는 이 실험에서 안 쓰므로(WB/매트릭스까지 우회하는
DCP용 경로라 카메라 JPEG과 직접 비교할 수 없음) 변경하지 않는다.

기존 호출부(12개 브랜드 population-fit 관련 코드, HNCS 구조 실험,
`tools/evaluate_hncs_structural.py` 등)는 전부 `decode_raw(path)`처럼
위치 인자 하나만 넘기므로 새 키워드 인자 추가로 영향 없음 - 회귀
테스트로 확인.

### 2. `tools/evaluate_fuji_demosaic.py` (신규)

```
python3 -m tools.evaluate_fuji_demosaic
```

- `fuji_pairs_manifest.csv`의 3행을 읽어 각 RAW를
  `decode_raw(raw_path)`(기본)와 `decode_raw(raw_path,
  demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT)`(DHT) 두 번 디코드.
- 같은 JPEG 타깃에 대해 `hybrid_engine.utils.evaluate.mean_delta_e`/
  `load_image_linear_for_evaluate`로 ΔE(CIEDE2000) 계산(HNCS 구조
  실험과 동일한 측정 방식 재사용 - 이 프로젝트의 표준 ΔE 관례).
- 페어별 (기본 ΔE, DHT ΔE, 개선 여부) 출력 + 3쌍 평균과 "3/3 방향
  일치" 여부만 요약(표본이 너무 작아 t-검정/부트스트랩 등은 시도하지
  않는다 - 그 자체가 오해를 부를 수 있음, HNCS 실험에서 배운 교훈).

### 3. 결과 기록

`hybrid_engine/EVALUATION.md`에 새 섹션 추가(이기든 지든 애매하든
정직하게, 이 프로젝트 관례):
- 3쌍 각각의 ΔE(기본 vs DHT) 표
- "3/3 방향 일치"인지, 아니면 엇갈리는지
- 결론: 방향이 일관되게 개선이면 "추가 표본 확보 후 재검증 가치 있음"
  으로, 엇갈리거나 악화면 "이 표본에서는 근거 부족/부적합"으로, 아주
  솔직하게 기록 - 어느 경우든 darktable 도입 여부는 이 스펙의 범위
  밖(별도 논의).

### 4. 건드리지 않는 것

- `apply_hncs()`(`brands/hasselblad.py`) - 이번 실험과 무관, 규칙상 항상
  보호.
- `brands/fuji.py`의 실제 `apply_*` 프리셋 함수들 - 이번 실험은
  `decode_raw()`라는 하위 유틸리티 레벨 비교일 뿐, 프리셋 함수는 애초에
  raw를 안 쓰고 이미 렌더링된 카메라 JPEG을 입력받는 구조라 이 실험
  결과와 직접 연결되지 않는다.
- `decode_raw_native()` - 위에서 설명한 이유로 범위 밖.

## 테스트 계획

- `decode_raw(path)`(인자 하나만 넘기는 기존 호출)가 이전과 동일한
  출력을 내는지 확인하는 회귀 테스트(예: 기존 테스트 스위트 전체
  재실행 - 새 키워드 인자가 기본 동작을 안 바꾼다는 걸 간접 확인).
- `decode_raw(path, demosaic_algorithm=DHT)`가 정상적으로 다른(하지만
  유효한 범위의) 이미지를 반환하는지 확인하는 단위 테스트 - 실제 RAW
  캐시 의존적이라 이 프로젝트의 기존 관례대로(`tools/analyze_camera_native_matrix.py`
  등) 커밋되는 자동화 테스트 없이 수동 실행으로 검증하고 보고서에
  결과를 남긴다.
- `tools/evaluate_fuji_demosaic.py`는 CSV 파싱 같은 순수 로직만
  단위 테스트, 실제 3쌍 비교는 수동 실행 + 보고서에 verbatim 기록
  (`tools/evaluate_hncs_structural.py`와 동일 패턴).

## 다음 단계(이 스펙 밖)

- DHT가 방향적으로 유의미해 보이면: 표본을 더 모으거나(다른 카메라
  리뷰 사이트), darktable-cli 도입을 별도로 브레인스토밍.
- Fuji raw+jpeg 페어 자체를 늘려서(현재 3쌍) 정식 raw 기반
  캘리브레이션(핫셀블라드처럼)을 시도하는 것도 완전히 별개의 후속
  프로젝트.
