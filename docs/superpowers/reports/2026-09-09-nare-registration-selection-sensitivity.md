# NARE registration selection sensitivity — GFX100RF Provia

[English](2026-09-09-nare-registration-selection-sensitivity.en.md)

2026-09-09의 registration 방법론 변경 뒤, 기존 GFX100RF Provia 51-frame
exploratory 결과와 현재 registration-passed 결과를 같은 scene ID 기준으로 다시
분해했다. 목적은 새 방법론이 단순히 geometry 오류를 줄였는지뿐 아니라,
**registration gate 자체가 보고되는 effect size를 얼마나 바꾸는지** 확인하는
것이다.

이 분석은 새 후보를 fit하지 않는다. 기존에 freeze된 다음 artifact만 읽는다.

- `nare_provia_exploratory_metrics_512px_2026-09.json`
- `nare_provia_exploratory_registration_512px_2026-09.json`
- `nare_provia_registered_report_512px_2026-09.json`
- `nare_provia_registered_report_1024px_2026-09.json`

분석 기준 revision은 `860abb164b7001c80fe67b44c39d5383f14d150d`다.
기계 판독용 결과는
`nare_provia_registration_selection_sensitivity_2026-09.json`에 함께 저장했다.

## 결과 1 — 현재 gate는 51개 중 32개만 통과

512px registration preflight는 51 input 중 **32 pass / 19 fail**이다.
실패 19개는 aspect-ratio mismatch 9개와 ECC correlation/translation/overlap
계열 geometry failure 10개로 나뉜다.

이는 이전 문서에 남아 있던 `37/51` 기록보다 더 엄격한 현재 방법론이다.
따라서 과거 37-scene 수치와 현재 32-scene 수치를 같은 experiment로 취급하면
안 된다.

## 결과 2 — registration 통과 여부와 pre-registration effect가 강하게 연관됨

아직 geometry correction을 적용하지 않은 **같은 51-frame exploratory metrics**를
현재 registration pass/fail ID로만 나눴다.

| subset | n | B0 mean ΔE00 | Provia mean ΔE00 | mean ΔE 개선 | aggregate 개선율 | 승/패 |
|---|---:|---:|---:|---:|---:|---:|
| 전체 intake | 51 | 20.7150 | 17.6103 | +3.1047 | +14.99% | 42/9 |
| registration pass | 32 | 18.5950 | 14.7033 | +3.8917 | **+20.93%** | 28/4 |
| registration fail | 19 | 24.2855 | 22.5064 | +1.7791 | **+7.33%** | 14/5 |
| └ aspect-ratio fail | 9 | 23.4781 | 20.8777 | +2.6004 | +11.08% | 8/1 |
| └ geometry fail | 10 | 25.0122 | 23.9722 | +1.0399 | **+4.16%** | 6/4 |

즉 현재 pass subset은 전체 51-frame 값보다 aggregate 개선율이 **+5.94%p** 높고,
fail subset보다 **+13.60%p** 높다.

scene별 절대 개선량 `(B0 ΔE - candidate ΔE)`의 pass-minus-fail 차이는
**+2.1126 ΔE**였다. 독립 group bootstrap 200,000회(seed=0) 95% CI는
**[+0.6194, +3.5669]**, label permutation 200,000회 two-sided p는
**0.01218**이다.

scene별 상대 개선율 평균으로 봐도 pass **20.87%**, fail **6.15%**,
차이 **+14.72%p**다. bootstrap 95% CI **[+7.51, +21.75]%p**,
permutation p **0.00099**였다.

### 해석 제한

이 차이를 "registration이 Provia를 더 좋게 만든다"고 읽으면 안 된다.
registration 실패 scene의 old exploratory ΔE는 애초에 geometry mismatch로
오염된 수치라 올바른 performance target이 아니다.

다만 **gate가 effect-size 분포와 독립적이지 않다**는 것은 분명하다. 따라서
registration 이후의 결과를 보고할 때 intake/exclusion accounting 없이 pass
subset effect만 제시하면 실제 방법론 변화가 candidate 개선으로 오인될 수 있다.

## 결과 3 — 실제 geometry correction 뒤 effect는 더 커짐

현재 등록된 32 scene을 실제로 translation registration한 report는 다음과 같다.

| scale | n | B0 mean ΔE00 | Provia mean ΔE00 | 개선율 | absolute-improvement 95% CI |
|---|---:|---:|---:|---:|---:|
| 512px | 32 | 15.9318 | 11.0512 | **+30.63%** | [+3.9864, +5.7387] |
| 1024px | 32 | 16.0787 | 11.4645 | **+28.70%** | [+3.7250, +5.4636] |

512→1024의 개선율 차이는 **−1.94%p**라 scale 자체에는 비교적 안정적이다.
반면 같은 32 pass scene의 *registration 전* exploratory metric은 +20.93%였으므로,
geometry correction + valid-overlap evaluation까지 포함한 현재 pipeline은 effect를
추가로 약 **+9.71%p** 바꾼다.

따라서 과거 51-frame unregistered `+14.99%`와 현재 32-frame registered
`+30.63%`를 "모델이 두 배 좋아졌다"고 비교하면 틀린다. 변화에는 최소 두 가지
방법론 효과가 같이 들어간다.

1. registration eligibility selection: `+14.99% → +20.93%`
2. accepted scene의 geometry correction/valid-overlap evaluation:
   `+20.93% → +30.63%`

## 방법론 결론

앞으로 NARE registered 결과에는 최소 다음을 같이 기록하는 것이 맞다.

- 원래 intake scene 수
- registration pass/fail 수와 failure category
- 가능하면 pass/fail subset의 pre-registration sensitivity
- registered effect와 scale sensitivity

이 분석은 **methodology sensitivity evidence**이며 ship evidence가 아니다.
GFX100RF pool은 여전히 lighting/scene taxonomy와 독립 contributor 조건을
충족하지 못하므로 NARE classification을 올리는 근거로 사용하지 않는다.
