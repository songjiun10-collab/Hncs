# 시작하기

*[English](START_HERE.en.md)*

[메인 README](../README.ko.md)로 돌아가기.

이 프로젝트가 뭘 하는지는 루트 [README](../README.ko.md)의 TL;DR을
먼저 읽는다. 이 문서는 "그다음 어디를 읽어야 하는지"만 다룬다 -
코드/방법론 내용 자체는 각 디렉토리의 `CLAUDE.md`와
`docs/methodology.md`에 있다.

## 디렉토리 지도

| 디렉토리 | 하는 일 | 규칙 문서 |
|---|---|---|
| `brands/` | 브랜드별 색감 근사 함수(`apply_*`) - 이 프로젝트가 실제로 출하하는 결과물 | [brands/CLAUDE.md](../brands/CLAUDE.md) |
| `core/` | `brands/*.py`가 공유하는 톤커브/LUT/통계/검증 헬퍼 | 전용 문서 없음 - [brands/CLAUDE.md](../brands/CLAUDE.md)에서 함께 다룸 |
| `tools/` | CLI + 연구용 `evaluate_*.py` 실험 스크립트 | [tools/CLAUDE.md](../tools/CLAUDE.md) |
| `hybrid_engine/` | 크로스 카메라 색변환 + 캘리브레이션/평가 엔진, `EVALUATION.md`(측정 기록) | [hybrid_engine/CLAUDE.md](../hybrid_engine/CLAUDE.md) |
| `gui/` | Tkinter 데스크톱 앱 - 기존 CLI를 감싸기만 함 | [gui/CLAUDE.md](../gui/CLAUDE.md) |
| `tests/` | `unittest` 테스트 스위트 | [tests/CLAUDE.md](../tests/CLAUDE.md) |
| `datasets/` | 커밋된 참조 CSV/JSON(공식 샘플 메타데이터, 시그니처 분석 결과) | [datasets/CLAUDE.md](../datasets/CLAUDE.md) |
| `docs/` | 이 디렉토리 - 상세 문서 | [docs/CLAUDE.md](CLAUDE.md) |

## 뭘 하려면 어디를 읽나

| 하려는 일 | 먼저 읽을 것 |
|---|---|
| 새 브랜드 추가 | [docs/methodology.md](methodology.md) + [brands/CLAUDE.md](../brands/CLAUDE.md) + 기존 population-fit 브랜드 파일 하나(예: `brands/nikon.py`)를 템플릿으로 복사 |
| 연구/실험 스크립트 작성·실행 | [tools/CLAUDE.md](../tools/CLAUDE.md) - `evaluate_*.py` 컨벤션(standalone, 통계는 `summarize()`) |
| 통계 판정 방식(유의성/CI) 이해 | [hybrid_engine/CLAUDE.md](../hybrid_engine/CLAUDE.md)의 "Statistics — non-negotiable" |
| GUI 탭 추가/수정 | [gui/CLAUDE.md](../gui/CLAUDE.md) |
| 문서 수정(이중언어 등) | [docs/CLAUDE.md](CLAUDE.md) |
| 테스트 작성 | [tests/CLAUDE.md](../tests/CLAUDE.md) - CI엔 이미지 데이터 없음 |
| 새 데이터셋/샘플 추가 | [datasets/CLAUDE.md](../datasets/CLAUDE.md) |
| 파일 단위로 뭐가 어디 있는지 찾기 | [docs/project_structure.md](project_structure.md) - 전체 파일 인덱스 |

## 절대 규칙 (요약)

전체 목록은 루트 [CLAUDE.md](../CLAUDE.md)의 "## Never" 참고. 가장 중요한 것: `brands/hasselblad.py`의 `apply_hncs()`와 다른 shipped `apply_*` 함수, `hybrid_engine/assets/profiles/*.json`/`*.dcp`는 연구 스크립트가 자동으로 덮어쓰지 않는다.
