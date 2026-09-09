# HNCS provenance trust 경계 재보강

[English](2026-09-09-provenance-trust-boundary-hardening.en.md)

2026-09-09 재감사에서 기존 Evidence Receipt 구현의 두 경로를 실제 반례로 다시
확인했다.

1. 로컬 호출자가 임의 Ed25519 키를 만들고 그 fingerprint를
   `HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256` / `HNCS_TRUSTED_EVALUATOR_SHA256`에
   직접 넣으면 EAGER가 `Verified`까지 승격될 수 있었다.
2. receipt 자체는 그대로 둔 채 `validation_passed`, `lockbox_passed`,
   `external_replication` CLI 값만 바꿔도 서명 무효화 없이 분류 결과를 바꿀 수
   있었다. `evidence_tier` 역시 receipt에 묶이지 않았다.

이번 변경은 로컬 검증과 독립 신뢰를 분리한다.

- `validate_receipt()`의 의미는 이제 **signature/artifact integrity 검증**이다.
  결과는 `signature_valid=True`를 반환하지만 `trusted`는 항상 `False`다.
  호출자가 지정한 key/evaluator fingerprint가 일치하는지만 검사하는 기능은 남아
  있지만, 그 일치 자체를 promotion 권한으로 해석하지 않는다.
- EAGER receipt는 `evidence_tier`와
  `validation_passed` / `lockbox_passed` / `external_replication` 세 값을 모두
  서명해야 한다. 누락이나 CLI 값과의 불일치는 fail-closed다.
- 일반 EAGER CLI는 어떤 환경변수나 self-signed key를 넣어도
  `trusted_provenance=True`를 만들지 않는다. 따라서 로컬 실행은 최대
  `Supported`이고 `Verified`는 별도의 trusted runner 경로가 생기기 전까지
  의도적으로 도달 불가능하다.
- NARE는 `Verified` 등급이 없으므로 의미를 분리했다. 유효한 signed receipt는
  `receipt_integrity`를 만족시켜 로컬 `Supported` 근거가 될 수 있지만,
  `trusted_provenance`를 주장하지 않는다.

## 남은 경계

독립 `Verified`를 실제로 발급하려면 저장소 내부 코드만으로는 부족하다. private
signing key, 승인 정책, 보호된 ref/environment처럼 **로컬 호출자가 선택할 수 없는
외부 trust anchor**가 필요하다. 이 세션의 GitHub 연결은 Actions secret/환경 보호
설정을 생성하거나 읽을 수 없으므로, 이번 커밋은 그 경로를 꾸며서 "완료"로 만들지
않고 로컬 promotion을 fail-closed로 막는 데서 멈춘다.

Supabase uploader의 기존 Supported/Verified/ship promotion 차단은 그대로 유지한다.
production look/profile과 dataset binary는 수정하지 않았다.

## 검증

회귀 테스트는 다음 공격을 포함한다.

- self-generated key + self-selected `HNCS_TRUSTED_*` 환경변수 → EAGER는 `Supported`
- signed receipt의 promotion attestation 하나만 CLI에서 뒤집기 → 거절
- receipt의 evidence tier와 CLI tier 불일치 → 거절
- NARE receipt 없음 → `Inconclusive`
- NARE 유효 signed receipt → `Supported`, 단 `trusted_provenance=False`

전체 suite 결과는 이 커밋의 GitHub Actions 실행으로 확인한다.
