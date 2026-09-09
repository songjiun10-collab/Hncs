# EAGER smoke 재현 결과 (2026-09-08)

[English](2026-09-08-eager-smoke-reproduction.en.md)

이 기록은 EAGER 통계 커널과 판정 게이트의 재현성을 확인하기 위한
**합성 입력 smoke run**이다. 실제 카메라 간 동일 물리 장면 데이터가 아니므로
cross-camera 일반화나 배포 성능의 근거로 사용할 수 없다.

## 입력 계약

- 독립 `scene_id`: 12개 (`scene-00`–`scene-11`)
- 조명 층: `daylight` 6개, `tungsten` 6개
- source body: `source-a`; target body: `target-b`
- 모든 행: `split=lockbox`, `evidence_tier=C`
- paired metric: baseline ΔE00 `10.0/10.2/10.4` 반복, candidate ΔE00 `8.0/8.1` 반복
- neutral: `4.0 → 3.0`; chromatic: `12.0 → 9.5`
- bootstrap: 20,000회, seed `0`
- controls: identity, target-reference shuffle, source-label shuffle,
  holdout rerun, chart positive control 모두 `true`
- robustness: source body와 두 조명 층 모두 `true`

## 재현 명령

입력 JSON 네 개를 위 계약대로 만든 뒤 다음 명령을 실행한다.

```bash
.venv/bin/python -m hybrid_engine.evaluation.eager_cli \
  --manifest /tmp/eager-repro/manifest.json \
  --metrics /tmp/eager-repro/metrics.json \
  --controls /tmp/eager-repro/controls.json \
  --robustness /tmp/eager-repro/robustness.json \
  --evidence-tier C --validation-passed --lockbox-passed \
  --bootstrap 20000 --seed 0
```

## 결과

| 항목 | 값 |
|---|---:|
| 독립 장면 수 | 12 |
| baseline 평균 ΔE00 | 10.200000000000001 |
| candidate 평균 ΔE00 | 8.049999999999999 |
| 평균 개선 | 2.15 |
| 평균 개선율 | 21.078431372549016% |
| paired bootstrap 95% CI | [2.0500000000000003, 2.241666666666667] |
| exact sign-test p | 0.00048828125 |
| ship gate | `true` |
| 분류 | `Supported` |

모든 게이트가 통과했지만 Tier C이고 외부 재현을 하지 않았으므로 `Verified`가
아니다. 이 수치는 실제 appearance 변환의 효과 크기가 아니라 커널이 scene-level
집계, paired 불확실성, subgroup, control, robustness 게이트를 같은 입력에서
결정론적으로 적용한다는 사실만 기록한다.

## 반증 확인

동일 입력에서 `target_reference_shuffle=false`로 바꾸면 결과는 다음과 같다.

```text
controls_passed=false
ship_gate_passed=false
classification=Rejected
failure=target_reference_shuffle
```

실제 Protocol 2R 결과를 추가할 때는 합성 결과와 별도 manifest·metric·provenance
hash를 사용하고, 이 smoke 수치를 덮어쓰지 않는다.
