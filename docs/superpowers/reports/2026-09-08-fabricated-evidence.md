# 일관된 가짜 증거의 Verified 승격 공격

[English](2026-09-08-fabricated-evidence.en.md)

> **정정(2026-09-08, trusted-provenance gate)**: 일반 EAGER JSON CLI는 이제
> `trusted_provenance=False`를 강제한다. 따라서 같은 가짜 bundle에
> `--external-replication`을 넣어도 최대 `Supported`다. classifier의
> `trusted_provenance=True`는 신뢰된 실행 caller만 전달할 수 있다.
> 이는 암호학적 인증이 아니라 fail-closed 정책 경계이며, 이미 신뢰된 caller가
> 거짓말하는 문제는 남아 있고 보고서에 명시한다.

기준 commit: `0da0c44086d0805e3ea87de536d66e1ed5a9c03f`는 최초 공격 재현이다.
현재 회귀 실행은 실제 EAGER CLI subprocess를 호출하며 classifier/통계/파일 읽기를
mock하지 않는다. 현재 결과: **receipt 없는 가짜 bundle은 Supported까지만 도달하고
Verified에는 도달하지 않는다.**

## 구성과 결과

실제로 읽을 수 있는 합성 PPM source 24개와 target 24개를 생성했다.
scene 간 픽셀·hash는 서로 다르고 각 source/target pair의 픽셀은 같다.
48개 파일 hash가 manifest와 일치함을 별도로 검사했다.
RAW/SOOC 촬영 corpus가 아니며, 여기서는 EAGER의 사전 계산 metric 경로를 공격한다.

manifest에는 evaluation 12개, lockbox 12개와 tier A를 주장했다.
metric은 이미지에서 계산하지 않고 baseline 10.0~10.8, candidate=baseline×0.8로
작성했다. neutral/chromatic 값도 유한한 양수이며 개선 방향이다.
controls·robustness는 전부 실제 boolean True로 작성했다.
실제 control 실행과 독립 재현 횟수는 모두 **0**이다.

| CLI에 공급한 조건 | 실제 관측 분류 |
|---|---|
| 파일 존재·48/48 hash 일치·조작 지표·모든 attestation | Supported |
| 위 조건에서 external-replication flag만 제거 | Supported |
| shuffle control을 실제 boolean False로 변경 | ship gate 실패 |
| 모든 source 파일을 변조하여 24개 hash 불일치 | Supported |
| source/target 이미지 48개 모두 삭제 | Supported |

조작 지표에서 CLI가 실제 계산한 값:

- n_scenes: 24
- mean_improvement_pct: 19.999999999999996
- 20,000회 bootstrap CI: [2.0549999999999997, 2.098333333333333]
- sign_test_p: 1.1920928955078125e-07

계산이 틀린 것이 아니다. **계산 입력의 출처와 실제 실험 수행을 검증하지 않는다.**
이 CI/p는 가짜 표에 대한 산술 결과이며 실제 사진 성능의 증거가 아니다.

## 원인과 경계

`eager_cli.build_report`는 JSON을 읽고 manifest/metric을 검사한다.
`evaluate_manifest_metrics`는 hash 형식을 검사하지만 실제 source/target 파일을
열어 hash를 재검증하거나 metric을 재계산하지 않는다. control은 boolean 선언이고
외부 재현도 CLI flag다. 따라서 진실성을 뒷받침하는 실행 증거가 없어도 승격된다.

파일 hash 재검사를 추가하면 변조/삭제 사례는 막을 수 있지만, 처음부터 hash까지
일치시킨 합성 증거의 Verified 승격은 막지 못한다. 같은 작성자가 생성한 서명이나
추가 JSON 필드도 독립 검증이 아니다. Verified를 실제 검증 의미로 쓰려면 측정 코드·
입력·출력·control 실행을 결합하고, 외부 재현은 별도 신뢰 주체의 증거로 확인해야 한다.

이번 변경은 공격 재현과 기록만 한다. production validator와 분류 정책을 바꾸지 않았다.
실제 RAW runner를 통과했다는 주장이 아니고, Supabase sync·배포·실제 calibration
registry 등록도 수행하지 않았다. 임시 합성 입력과 CLI 전체 report는 실행 종료 시 삭제되며
아래 요약 JSON에는 실제 실험으로 오인하지 않도록 SYNTHETIC 경고가 포함된다.

## 재현

[공격 코드](2026-09-08-fabricated-evidence-probe.py) ·
[실제 실행 결과](2026-09-08-fabricated-evidence-results.json)

저장소 루트에서:

```bash
~/.hncs-hybrid-venv312/bin/python3 docs/superpowers/reports/2026-09-08-fabricated-evidence-probe.py --out /tmp/hncs-fabricated-evidence-results.json
```

문서의 최초 `Verified` 결과는 trusted-provenance gate 이전의 historical characterization이다.
현재 스크립트는 같은 합성 bundle을 다시 실행해 receipt 없는 결과가
`Verified`로 올라가지 않는지를 assert하는 보안 회귀 probe다.
