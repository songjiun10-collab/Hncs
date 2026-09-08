# HNCS Evidence Receipt — 최소 provenance/authentication 계층

[English](2026-09-09-evidence-receipt.en.md)

`0da0c44`와 `3e27c7a`의 공격에서 확인한 문제는 metric 숫자의 유한성이나
파일 hash 형식이 아니었다. 외부 JSON이 어떤 입력·코드·설정으로 실제 생성됐는지
검증할 연결고리가 없었다.

이번 구현은 `hybrid_engine/evaluation/evidence_receipt.py`에 canonical JSON과
Ed25519 receipt 검증을 추가했다. receipt는 다음을 서명한다.

- manifest, metrics, controls, robustness의 SHA-256
- evaluator SHA-256과 git commit SHA
- 실행 command, timestamp, run ID, optional parent run ID
- 서명 key ID와 Ed25519 signature

EAGER CLI는 `--receipt`와 `--receipt-public-key`를 함께 받아 네 artifact의 현재
hash와 서명을 검증한다. 둘 중 하나가 없거나 hash가 달라지면 거절한다.
receipt가 유효하지 않으면 `trusted_provenance=False`이며, `--external-replication`만으로
`Verified`가 되지 않는다. 유효한 receipt를 검증한 trusted runner만 classifier에
`trusted_provenance=True`를 전달할 수 있다.

```bash
python -m hybrid_engine.evaluation.eager_cli \
  --manifest manifest.json --metrics metrics.json \
  --controls controls.json --robustness robustness.json \
  --git-sha "$GIT_COMMIT_SHA" \
  --evidence-tier C --validation-passed --lockbox-passed \
  --external-replication \
  --receipt run.receipt.json --receipt-public-key ci-ed25519.pub
```

기존 JSON CLI는 `Supported`까지의 호환성을 유지한다. receipt 없는 JSON만으로
`Verified`를 만들 수 없게 한 것이 핵심 fail-closed 경계다.

## 검증 결과

- signed receipt의 정상 hash chain: 통과
- metrics 변경 후 receipt 검증: 실패
- unsigned receipt: 실패
- 유효 receipt가 있는 EAGER report: `Verified`
- receipt 없이 external replication만 주장한 report: `Supported`
- 전체 suite: 1,425개 통과

## 한계

이 계층은 “지정된 artifact와 evaluator identity를 trusted runner가 서명했다”는
것을 인증한다. 데이터가 현실을 정직하게 표현하는지, evaluator가 내부에서 올바른
코드를 실행했는지까지 수학적으로 증명하지 않는다. Ed25519 private key를 가진
trusted runner가 거짓말하면 이 계층도 거짓을 인증할 수 있다. 따라서 private key는
GitHub CI 같은 별도 실행 환경에 두고, local run은 최대 `Supported`로 제한해야 한다.

서명 private key를 저장소나 report에 넣지 않았다. 이번 변경은 production look/profile,
기존 dataset, Supabase registry를 수정하지 않는다.
