# 학습/잔차 LUT 보관소

`calibrate_profile.py --mode learned`(톤)/`--mode hue`(hue)가 만드는 학습
LUT(npy)이 여기 저장된다. 파일 자체는 커밋하지 않음(재현 가능한
산출물이라) - 아래 명령으로 재생성.

```
python3 -m hybrid_engine.calibrate_profile --mode learned
python3 -m hybrid_engine.calibrate_profile --mode hue
```

## hue 보정 LUT 실측 결과 (2026-07, 음성 결과로 기각)

`evaluation/fidelity.py`가 측정한 평균 |Δhue| 34.29도(`hybrid_engine/EVALUATION.md`)를
근거로 "톤이 아니라 hue가 병목"이라는 가설을 세우고, 13쌍에서 순환
1D hue LUT(입력 hue별 chroma 가중 순환평균 보정량, 36 bin)을 학습해서
비교했다:

- hue 보정 전 ΔE(CIEDE2000): 14.85
- hue 보정 후 ΔE: 14.54 (+2.1%)

**채택 안 함.** 톤 LUT(+4.9%)보다도 개선폭이 작다. 큰 |Δhue| 숫자에
비해 ΔE 개선이 미미한 이유로 두 가지를 의심 중:

1. **CIEDE2000의 hue 항(S_H)은 채도가 낮을수록 가중치가 작아진다** -
   |Δhue| 34도라는 평균은 무채색 근처(hue가 원래 노이즈에 민감한 저채도
   영역)가 크게 끌어올렸을 가능성이 있고, 그런 픽셀은 애초에 ΔE00에
   거의 기여하지 않는다.
2. **hue 하나만 입력으로 쓰는 전역 LUT은 장면/색상군(피부톤·하늘·식물
   등, "memory color")별로 다른 보정이 필요한 실제 카메라 렌더링 방식을
   못 담는다** - 실제 카메라 색 렌더링은 hue 각도 하나가 아니라
   L/hue/chroma 조합(3D)에 의존한다는 방증.

**더 중요한 발견: 톤(L)만 고쳐도, hue만 고쳐도 개선폭이 둘 다 5%
미만이라는 게 "병목이 hue다"라는 가설 자체를 약화시킨다.** 두 축을
독립적으로 1D LUT으로 보정하는 접근 자체의 한계로 보는 게 더 정확함 -
잔차가 채널 하나로 분해되지 않고 L/a/b가 결합된(joint) 형태라는 뜻.
다음 후보는 개별 축의 학습 LUT이 아니라 **3D 잔차 LUT**(L/a/b 조합을
입력으로 받는) 또는 Phase 2(공간 연산)일 가능성이 높음.

## 톤 보정 LUT 실측 결과 (2026-07, 음성 결과로 기각)

13쌍의 핫셀블라드 raw+jpeg 페어에서 apply_hncs_learned 방식(bin별 픽셀
대응 평균)으로 L채널 1D LUT을 학습해서 파라메트릭 톤과 비교했다:

- 파라메트릭 profile ΔE(CIEDE2000): 14.85
- 학습 LUT ΔE: 14.12 (+4.9%)

**채택 안 함.** 사전 기준(>20% 개선)에 못 미치고, 학습에 쓴 페어
그대로에서 잰 in-sample 수치라(교차검증 없음) 실제 개선폭은 이보다도
작을 것. 원래 HNCS 파이프라인에서는 같은 방식이 RMSE 23.3→15.4라는 큰
개선을 냈는데 여기선 거의 효과가 없다는 게 오히려 유의미한 발견 -
hybrid_engine의 ΔE 병목은 L채널 톤커브 모양이 아니라 a/b(채도·hue)
잔차와 공간적 요인(메타메리즘 포함, `core/color_matrix.py` docstring
참고)이라는 진단이 실측으로 확정됨. Phase 2/3(공간 연산, 3D 잔차 LUT)이
다음 후보인 이유.
