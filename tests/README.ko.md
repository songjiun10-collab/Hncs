# tests/

*[English README](README.md)*

`unittest` 기반 테스트 스위트(pytest 등 외부 의존성 추가 없음 -
`requirements.txt`의 최소 의존성 원칙 유지). `core/curve.py`(톤커브
수학, 경계조건/단조성/연속성) / `core/stats.py`(population 통계
계산) / `core/validation.py`(무결성 검증, CDN 손상 패턴 재현) /
`core/engine.py`(population-fit 엔진) / `brands/*.py`(모든 `apply_*`
룩 함수의 shape/dtype 보존, 후지 프리셋 개수 일관성) / `tools/
fuji_chart_calibrate.py`(크롭박스 추출, delta 집계) / `tools/
download.py`(imaging-resource.com HTML 파싱, 필터링, 구글드라이브
URL 분류 - 네트워크 호출은 mock 처리) / `datasets/*/texture_signature.json`
전체(sharpening/micro_contrast/noise가 브랜드 간 합리적 범위 안에
있는지 - 소니 스케일 버그류의 자릿수 오류를 잡는 회귀 가드) /
`core/lut.py` / `core/denoise.py` / `tools/iso_noise.py`(패치그리드
off-by-one 버그 회귀 테스트 포함) / `core/log_pipeline.py`(노출 조정,
Log 인코딩, `.cube` LUT 적용, 지원되는 `LOG_SPACES` 전 항목) /
`hybrid_engine/`(정규화/톤/색/색매트릭스/파이프라인/ΔE 평가/EXIF
브랜드 판별과 프리셋 역변환, 엔드투엔드) / `core/dcp_export.py`(DCP
TIFF 구조, write/read 왕복, 배포된 X2D II 프로필이 실제 fit 리포트와
물리적으로 일치하는지)를 다룬다.

`.github/workflows/tests.yml`이 push/PR마다 이 스위트를 자동
실행한다.

```
python3 -m unittest discover -s tests -v
```

`core`/`brands`/`tools`/`hybrid_engine` import 경로가 제대로 풀리도록
저장소 루트에서 실행할 것.
