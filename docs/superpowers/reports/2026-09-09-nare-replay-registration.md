# NARE 재실행과 사진별 registration 검증

[English](2026-09-09-nare-replay-registration.en.md)

이전 완료 보고를 정정한다. 파일 존재·hash·자체 서명만으로는 계산 실행이
입증되지 않았다. receipt가 있는 NARE report는 이제 로컬의 고정 Provia,
identity foundation, 512px runner를 실제 실행하고 제출 metrics 전체와 대조한다.
receipt의 command는 실행하지 않는다. 일치하지 않거나 실행이 실패하면 거부한다.
평가에는 재계산된 records를 사용한다. 새로운 evaluator나 scale은 별도 지원이 필요하다.

현재 runner는 semantic ROI 지표를 생성하지 않는다. 제출 JSON으로 이를 보충할
수 없으며, 재실행에 성공한 현재 runner 결과도 subgroup gate 미충족으로
Inconclusive에 머문다. 이는 Supported를 단순 무결성 등급으로 재정의하는 것이 아니다.
실제 사진의 진실성·촬영 provenance나 독립 runner 인증은 여전히 증명하지 않는다.
수치가 runtime 차이로 바뀌면 정확 대조가 실패하므로 같은 환경에서 재생성해야 한다.

여러 사진의 scene 평균은 유지하고 registration은 frames 배열로 보존한다.
모든 사진을 자기 해상도와 이동 벡터로 검증한다. 서로 다른 사진의 x/y 최대값을
합치거나 첫 사진의 진단으로 실패를 숨기지 않는다. 단일 사진 형식은 유지한다.

회귀: tests.test_nare_execution_boundary는 이동 벡터·scale·실패·누락 진단,
조작 수치·semantic 삽입·정상 대조·scene 순서 및 실제 runner 재실행을 검사한다.
양성 대조는 디코드만 mock하고 registration, 색 계산, 서명 검증과 report를 실행한다.
