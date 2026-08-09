# CIEDE2000 (kL,kC,kH) 가중치 재검증 (설계)

## 배경

사용자가 공유한 논문("디지털 영상의 색차 측정을 위한 CIEDE2000 최적화",
이수연·곽영신, 한국색채학회 2014 춘계학술대회)이 디지털 영상 색차
측정에서 CIEDE2000 표준 기본값 (kL,kC,kH)=(1,1,1) 대신 정신물리학
실험(STRESS 지표 최적화)으로 (kL,kC,kH)=(4.1, 1.1, 1.6)이 더 잘
맞는다는 결과를 냈다. 논문 자체도 CIE Central Bureau(2011)가 디지털
영상 색차 계산에는 kL 조정이 필요하다고 밝힌 걸 인용한다.

DBpia/KCI 둘 다 이 환경에서 접근 차단(paywall + 프록시 차단)이라 논문
원문을 직접 못 열었다 - 사용자가 캡처한 화면(2.5/2.6절, 그림3/4)과
DBpia AI 요약카드로 확인한 값(정확한 (4.1, 1.1, 1.6))에 의존한다.
**출처 확실성**: 공식 학회 발표 논문(공식) - 다만 이 프로젝트가
원문 전체(방법론/한계 절)를 직접 읽고 검증한 건 아니다.

이 프로젝트는 `hybrid_engine/utils/evaluate.py`의 `mean_delta_e()`/
`delta_e_map()`으로 ΔE(CIEDE2000)를 재는데, 전부 `colour.delta_E(...,
method="CIE 2000")`를 인자 없이 호출해 (1,1,1)이 암묵적으로 쓰인다.
이 함수를 직접 쓰는 곳이 10개 파일(`hybrid_engine/main.py`,
`evaluation/metrics.py`, `calibrate_profile.py`,
`tests/test_hybrid_engine.py`, `tools/evaluate_hncs_blend.py`,
`evaluate_hncs_structural.py`, `evaluate_fuji_demosaic.py`,
`evaluate_darktable_vs_rawpy.py`, `evaluate_chromatic_aberration.py`)고,
`hybrid_engine/EVALUATION.md`에 기록된 수십 건의 실험 결과 전부 이
기본값으로 측정됐다.

## 기술적 제약: colour-science가 임의 kL/kC/kH를 지원 안 함

이 컨테이너에 설치된 `colour-science` 0.4.7(pip 최신)의
`delta_E_CIE2000(Lab_1, Lab_2, textiles=False)`는 `textiles=True`일 때
kL=2 고정을 쓰는 것 말고는 kL/kC/kH를 받는 인자가 아예 없다(직접 소스
확인). 대신 최종 결합 전 중간값(S_L, S_C, S_H, ΔL', ΔC', ΔH', R_T)을
반환하는 내부 함수 `colour.difference.delta_e.intermediate_attributes_CIE2000(Lab_1,
Lab_2)`가 있다 - 이걸 재사용해서 커스텀 kL/kC/kH로 직접 결합하면
라이브러리의 기하 계산(hue 회전, RT 등 복잡한 부분)을 재구현할 필요
없이 안전하게 확장 가능:

```python
d_E = sqrt((ΔL'/(kL·S_L))² + (ΔC'/(kC·S_C))² + (ΔH'/(kH·S_H))²
           + R_T·(ΔC'/(kC·S_C))·(ΔH'/(kH·S_H)))
```

kL=kC=kH=1.0으로 두면 `colour.delta_E_CIE2000`의 기존 계산과 **정확히
같은 값**이 나와야 한다(회귀 테스트로 확인 - 이게 깨지면 기존에 기록된
모든 ΔE 수치의 재현성이 깨진다).

**설계 단계에서 직접 검증함**: 랜덤 Lab 1000쌍으로 위 결합식을
`colour.delta_E(..., method="CIE 2000")`와 kL=kC=kH=1.0에서 비교 -
최대 절대오차 0.0(완전 일치). `colour.delta_E(..., textiles=True)`
(내부적으로 kL=2 고정)와도 kL=2.0으로 비교해 완전 일치 확인 -
`intermediate_attributes_CIE2000` 재사용 접근이 옳다는 교차검증.
(4.1,1.1,1.6)로 계산하면 같은 랜덤 데이터에서 ΔE가 대략 절반 수준으로
낮아짐(kL=4.1이 밝기차 기여를 크게 낮추므로) - 방향성이 물리적으로
말이 된다.

## 설계

### 1. `hybrid_engine/utils/evaluate.py` 확장

```python
from dataclasses import astuple
from colour.difference.delta_e import intermediate_attributes_CIE2000

def delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=1.0, kC=1.0, kH=1.0):
    """CIEDE2000을 커스텀 (kL, kC, kH)로 계산. colour-science의
    delta_E_CIE2000()은 kL/kC/kH를 임의로 못 받아서(textiles=True 때
    kL=2 고정만 지원, 소스 확인함) 결합 전 중간값을 재사용해 직접
    결합한다 - 기하 계산(hue 회전 등)은 colour-science 걸 그대로 쓰므로
    재구현 위험이 없다. kL=kC=kH=1.0이면 colour.delta_E(method="CIE
    2000")과 동일해야 한다(tests에서 회귀 확인)."""
    S_L, S_C, S_H, delta_L_p, delta_C_p, delta_H_p, R_T = astuple(
        intermediate_attributes_CIE2000(Lab_1, Lab_2))
    return np.sqrt(
        (delta_L_p / (kL * S_L)) ** 2
        + (delta_C_p / (kC * S_C)) ** 2
        + (delta_H_p / (kH * S_H)) ** 2
        + R_T * (delta_C_p / (kC * S_C)) * (delta_H_p / (kH * S_H))
    )
```

`mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000", kL=1.0,
kC=1.0, kH=1.0)`와 `delta_e_map(...)`은 `method=="CIE 2000"`일 때
`delta_E_CIE2000_weighted`로 라우팅(다른 method는 지금처럼
`colour.delta_E` 그대로 - kL/kC/kH가 의미 없는 다른 공식까지 건드리지
않음). 전부 기본값 1.0이라 **기존 호출부(main.py, calibrate_profile.py
등 10개 파일)는 전혀 안 바뀜** - 시그니처만 늘어난다.

### 2. 5개 재검증 대상 스크립트에 `--kl/--kc/--kh` 추가

`evaluate_hncs_blend.py` / `evaluate_hncs_structural.py` /
`evaluate_fuji_demosaic.py` / `evaluate_darktable_vs_rawpy.py` /
`evaluate_chromatic_aberration.py` 각각에:
- `argparse`에 `--kl/--kc/--kh`(기본 1.0) 추가
- `mean_delta_e()`를 호출하는 leaf 함수들(`_blend_combo_mean`/
  `run_loocv`/`fit_chroma_lut_params`/`structural_delta_e`/
  `apply_hncs_delta_e`/`compare_pair`/`check_determinism`/
  `delta_e_for` 등, 파일별로 다름)에 `kL=1.0, kC=1.0, kH=1.0` 파라미터를
  추가해서 `main()`부터 그대로 흘려보냄 - 그리드서치 기준 자체가
  ΔE이므로(예: `fit_weighted_chroma_lut`의 SAT_MULT_GRID x
  HUE_SHIFT_GRID 탐색) 최종 측정만이 아니라 피팅 전체가 새 가중치로
  다시 돈다.

### 3. `evaluate_hncs_blend.py`의 하드클러스터 기준선 문제

`HARD_CLUSTER_DE`(:79)는 **(1,1,1)로 측정된 하드코딩 상수**
(`hybrid_engine/EVALUATION.md`에서 복사됨)다. 블렌딩 쪽만 새 가중치로
재고 하드클러스터는 옛 상수를 그대로 쓰면 다른 자로 잰 두 값을
비교하게 된다. 나머지 4개 스크립트는 비교 양쪽을 같은 실행 안에서
라이브로 재므로 이 문제가 없다(직접 확인함 - `HARD_CLUSTER_DE` 같은
패턴의 하드코딩 상수는 `evaluate_hncs_blend.py`에만 있음).

**해결**: `evaluate_hncs_structural.py`의 새 가중치 실행(하드클러스터
LOO ΔE를 계산하는 `run_loocv()`)을 먼저 끝내서 새
`HARD_CLUSTER_DE_WEIGHTED` 값을 얻은 뒤, 그 값을
`evaluate_hncs_blend.py`에 새 상수로 추가(`HARD_CLUSTER_DE`는 그대로
두고 - 이건 기존 (1,1,1) 결과 재현용, 새 상수를 병행 추가)해서
`--weighted` 모드일 때 그쪽을 쓰게 한다. 즉 실행 순서는
`evaluate_hncs_structural.py`(가중) 완료 → 그 출력으로
`evaluate_hncs_blend.py`(가중) 시작, 나머지 3개
(`evaluate_fuji_demosaic.py`/`evaluate_darktable_vs_rawpy.py`/
`evaluate_chromatic_aberration.py`)는 의존성 없이 처음부터 병렬.

### 4. 실행

5개 스크립트 전부 `nohup ... &`로 백그라운드(hncs_structural과 나머지
3개는 즉시 시작, hncs_blend는 hncs_structural 완료 후 시작), `Monitor`로
지켜본다. 실험당 원래 걸린 시간(hncs_blend 74쌍 4시간22분,
chromatic_aberration 83쌍 약 60~70분 등)과 비슷하거나 조금 더 걸릴 수
있음(그리드서치 자체를 다시 돌리므로) - 총 5시간 이상 예상.

### 5. 기록

각 실험의 `hybrid_engine/EVALUATION.md` 절 **밑에 새 하위절 추가**
(정정 아님 - 기존 (1,1,1) 결과가 틀린 게 아니라 다른 자로 잰 별도
결과이므로 `> 정정(...)` 블록쿼트를 쓰지 않는다):

```markdown
### (kL,kC,kH)=(4.1,1.1,1.6) 가중치 재검증 (2026-08-09)

<이 논문 인용 - 출처 확실성 명시> 결과: <실제 판정>. 기존
(1,1,1) 판정(<기존 판정>)과 <같음/다름>.
```

판정이 바뀐 실험이 하나라도 있으면(예: 판정 보류였던 게 유의미해지거나
반대로 뒤집히는 경우) 구현 완료를 보고할 때 텍스트로 명시한다 - 별도
요약 문서는 새로 안 만든다(5건이라 EVALUATION.md의 각 절만 봐도 충분).

## 절대 안 건드리는 것

- `brands/hasselblad.py`의 `apply_hncs()`와 그 파라미터. 이 재검증은
  기존 모델을 새 가중치로 다시 피팅하는 게 아니라, **같은 실험
  파이프라인을 다른 자로 다시 재는 것**뿐이다 - `apply_hncs()`는 애초에
  raw+jpeg 그리드서치로 (1,1,1) 기준 확정된 값이고 이 스펙 범위에서
  재확정하지 않는다.
- `hybrid_engine/assets/profiles/hasselblad.json` / `*.dcp`.
- `mean_delta_e`/`delta_e_map`의 **기본값**(1.0,1.0,1.0) - 이번 변경은
  선택 인자 추가일 뿐, 기존 10개 호출부의 동작은 바뀌지 않는다.

## 테스트

- `delta_E_CIE2000_weighted(Lab_1, Lab_2, 1.0, 1.0, 1.0)` ==
  `colour.delta_E(Lab_1, Lab_2, method="CIE 2000")` (허용오차 내) -
  임의 Lab 값 여러 개로 확인. 이게 이 스펙 전체의 안전망이다.
- `mean_delta_e`/`delta_e_map`을 기존 인자로만 호출했을 때
  (`tests/test_hybrid_engine.py`의 기존 어서션들) 값이 전혀 안 바뀌는지
  - 기존 테스트가 그대로 통과하는 것 자체가 회귀 증거.
  - `TestSummarizeRecordedRun` 패턴 - 각 스크립트의 새 가중치 실행
  결과를 하드코딩해서 재현 테스트로 남긴다(기존 관례 그대로).
