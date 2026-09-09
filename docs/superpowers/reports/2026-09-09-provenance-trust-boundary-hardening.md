# HNCS provenance trust 경계 재보강

[English](2026-09-09-provenance-trust-boundary-hardening.en.md)

2026-09-09 재감사에서 로컬 호출자가 임의 Ed25519 키를 만들고 그 fingerprint를
`HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256` / `HNCS_TRUSTED_EVALUATOR_SHA256`에 직접
설정하면 EAGER가 `Verified`에 도달할 수 있음을 재현했다. 환경변수는 로컬 호출자가
선택할 수 있으므로 독립 trust anchor가 아니다.

동시에 promotion에 영향을 주는 `evidence_tier`, `validation_passed`,
`lockbox_passed`, `external_replication`이 receipt와 독립적이던 경계도 보강했다.
현재 EAGER receipt의 signed `run_config`는 bootstrap/seed와 함께 이 네 값을 묶는다.
같은 receipt를 유지한 채 CLI 값만 바꾸면 `run_config` 검증에서 fail-closed 된다.

현재 일반 EAGER CLI는 signature/artifact integrity와 signer authority를 분리한다.
`validate_receipt()`는 유효한 서명에 대해 `signature_valid=True`를 반환하지만
`trusted=False`다. 로컬 CLI는 `trusted_provenance=True`를 만들지 않으므로 최대
`Supported`이며, `Verified`는 로컬 호출자가 선택할 수 없는 별도의 trusted runner가
생기기 전까지 의도적으로 도달 불가능하다.

NARE는 `Verified` 등급이 없으므로 valid signed receipt를 artifact-integrity 근거로만
사용한다. `Supported`는 receipt integrity를 요구하지만 `trusted_provenance`를 주장하지
않는다. bootstrap/seed 역시 signed `run_config`와 일치해야 한다.

진짜 `Verified` 발급에는 private signing key, 승인 정책, protected ref/environment처럼
로컬 호출자가 선택할 수 없는 외부 trust anchor가 필요하다. 이 세션의 GitHub 연결은
Actions secret/protected-environment 설정을 만들 수 없으므로 그 경로를 꾸며 완료 처리하지
않았다. 기존 Supabase uploader의 Supported/Verified/ship promotion fail-closed 차단은 유지한다.
