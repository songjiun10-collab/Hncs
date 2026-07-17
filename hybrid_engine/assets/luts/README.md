# 학습/잔차 LUT 보관소

`calibrate_profile.py --mode learned`가 만드는 학습 톤 LUT(npy)이 여기
저장된다. 파일 자체는 커밋하지 않음(재현 가능한 산출물이라) - 아래
명령으로 재생성.

```
python3 -m hybrid_engine.calibrate_profile --mode learned
```

## 실측 결과 (2026-07, 음성 결과로 기각)

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
