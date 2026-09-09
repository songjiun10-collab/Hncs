# HNCS Evidence Receipt — 최소 provenance/authentication 계층

[English](2026-09-09-evidence-receipt.en.md)

> **정정(2026-09-09, registry 신뢰 선언 위조 재감사)**: 아래 완료 주장은
> 독립 실행 인증을 입증하지 않는다. `trusted_provenance: true`와 가짜
> receipt 객체만 추가하면 registry의 기존 검사 두 개를 모두 우회했다.
> 회귀 테스트의 다섯 조합(Verified/Supported 각각 ship true/false,
> Inconclusive + ship true)에서 수정 전 모두 예외 없이 통과했다.
> 현재 uploader는 Supported/Verified 또는 ship=true 업로드를 쓰기 전에
> 거절한다. 이는 임시 fail-closed 제한이며, 신뢰된 ingestion 구현이 아니다.
> Exploratory/Inconclusive/Rejected 연구 업로드는 계속 가능하다.
> 제출자가 지정한 공개키의 서명 검증은 그 키의 신뢰성을 보장하지 않는다.
> EAGER CLI는 `HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256`가 설정되고 공개키
> fingerprint가 일치할 때만 receipt-backed `Verified`를 허용한다. 환경변수가
> 없으면 같은 receipt도 `Supported`에 머문다.
> evaluator hash도 `HNCS_TRUSTED_EVALUATOR_SHA256`와 일치해야 한다.
> CLI의 등급, RAW/JPEG 실파일 검증, evaluator/config 검증 및 독립 replay는
> 여전히 별도 보강이 필요하다. 이 변경은 기존 원격 기록을 감사하거나
> 정정하지 않으며 service-role 소유자의 직접 DB 쓰기도 방어하지 않는다.

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
export HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256="$(openssl dgst -sha256 -binary ci-ed25519.pub | xxd -p -c 256)"
export HNCS_TRUSTED_EVALUATOR_SHA256="$(shasum -a 256 hybrid_engine/evaluation/eager_cli.py | awk '{print $1}')"
python -m hybrid_engine.evaluation.eager_cli \
  --manifest manifest.json --metrics metrics.json \
  --controls controls.json --robustness robustness.json \
  --git-sha "$GIT_COMMIT_SHA" \
  --evidence-tier C --validation-passed --lockbox-passed \
  --external-replication \
  --receipt run.receipt.json --receipt-public-key ci-ed25519.pub
```

NARE CLI도 같은 receipt 경계를 사용하며 manifest, metrics, controls 세 artifact의
hash chain을 검증한다. 따라서 receipt 없는 외부 metrics JSON은 `Inconclusive`로
남고, 서명된 receipt를 검증한 실행만 `Supported`가 될 수 있다. EAGER의 기존
JSON 경로는 `Supported`까지의 호환성을 유지하지만 `Verified`에는 receipt가
필요하다.

## 검증 결과

- signed receipt의 정상 hash chain: 통과
- metrics 변경 후 receipt 검증: 실패
- unsigned receipt: 실패
- 유효 receipt가 있는 EAGER report: `Verified`
- receipt 없이 external replication만 주장한 report: `Supported`
- NARE receipt 없는 plausible metrics: `Inconclusive`
- NARE 유효 receipt-backed report: `Supported`
- 전체 suite: 1,454개 통과 (현재 checkout 재실행)

## NARE trusted-runner 재감사 (2026-09-09)

NARE CLI도 이제 EAGER와 동일하게 trusted receipt public-key fingerprint와
evaluator fingerprint가 환경에 pin되어 있을 때만 receipt를 provenance gate에
반영한다. 임의 Ed25519 키로 서명한, 형식상 유효한 receipt는 hash chain 검증을
통과해도 `trusted_provenance=False` 및 `Inconclusive`로 남는다. 두 fingerprint를
모두 일치시킨 실행만 `Supported` 경로에 들어간다. 회귀 검증은 `tests.test_nare_cli`
2개이며 전체 suite는 1,454개 통과했다.

또한 NARE CLI의 `--receipt`와 `--receipt-public-key`는 이제 반드시 함께
지정해야 한다. 한쪽만 지정한 호출은 receipt를 묵살한 채 진행하지 않고 즉시
실패한다.

receipt의 `git_sha`도 이제 축약형을 받지 않고 40자리 full commit SHA만 받는다.
짧은 revision 표기는 registry 메타데이터에만 남기고, 실행 provenance identity에는
사용하지 않는다.

추가로 registry sync의 `ship_gate_passed`, `provenance_passed`,
`external_replication`은 이제 Python truthiness가 아니라 JSON boolean `true`만
승인한다. 문자열 `"false"` 같은 fabricated 값은 저장 상태를 complete/ship으로
오염시키지 않는다.

NARE report의 `paired` 결과에도 `bootstrap_draws`와 `bootstrap_seed`를 기록해
metrics와 통계 설정이 함께 고정되도록 했다.

## 한계

이 계층은 “지정된 artifact와 evaluator identity를 trusted runner가 서명했다”는
것을 인증한다. 데이터가 현실을 정직하게 표현하는지, evaluator가 내부에서 올바른
코드를 실행했는지까지 수학적으로 증명하지 않는다. Ed25519 private key를 가진
trusted runner가 거짓말하면 이 계층도 거짓을 인증할 수 있다. 따라서 private key는
GitHub CI 같은 별도 실행 환경에 두고, local run은 최대 `Supported`로 제한해야 한다.

서명 private key를 저장소나 report에 넣지 않았다. 이번 변경은 production look/profile,
기존 dataset, Supabase registry를 수정하지 않는다.
