# Onboarding Entry-Point Docs — Design

> Sub-project 1 of 4 in the "레포 전체 대규모 리팩토링" initiative
> (maintainability + readability for other contributors). The other three
> — brand wrapper-function consolidation, a `tools/` adopted-vs-rejected
> index, and splitting `tools/calibrate.py` — get their own specs later.

## Problem

The repo has thorough documentation (root `CLAUDE.md`, seven per-directory
`CLAUDE.md` files, `docs/*.md`/`.en.md`), but nothing tells a first-time
reader **what order to read it in** or **which doc answers which
question**. `docs/project_structure.md` indexes every file but assumes
you already know which directory you care about.

## Goals

- A new visitor can go from "just cloned this" to "I know which
  `CLAUDE.md` to read before touching directory X" in under a minute.
- Zero new conventions to maintain going forward beyond what
  `docs/CLAUDE.md` already mandates (bilingual pairs).

## Non-goals

- Not rewriting or duplicating any existing doc's content — this is pure
  navigation/index, linking out to the real sources.
- Not touching `hybrid_engine/` internals docs (out of scope by
  `docs/CLAUDE.md` convention, same as `project_structure.md`).

## Design

Two pieces, both additive:

### 1. A short pointer in `README.md` / `README.ko.md`

New `## Where to start reading` / `## 어디부터 읽을까` section, inserted
immediately after the TL;DR bullet list and before the two demo images.

`README.md` (English), exact text:

```markdown
## Where to start reading

New here? Read in this order: this README's [Supported
Brands](#supported-brands) table for what's shipped, then
[docs/project_structure.en.md](docs/project_structure.en.md) for the
file-level map, then the `CLAUDE.md` in whichever directory you're about
to touch (each area documents its own rules — `brands/`, `core/`,
`tools/`, `hybrid_engine/`, `gui/`, `tests/`, `datasets/`, `docs/`).
[docs/START_HERE.en.md](docs/START_HERE.en.md) has the full directory map
plus a "want to do X → read Y" table.
```

`README.ko.md` (Korean), exact text:

```markdown
## 어디부터 읽을까

처음이라면 이 순서로: 이 README의 [지원 브랜드](#지원-브랜드) 표로 뭐가
있는지 확인 -> [docs/project_structure.md](docs/project_structure.md)로
파일 단위 지도 확인 -> 건드릴 디렉토리의 `CLAUDE.md`(각 영역이 자기
규칙을 직접 문서화함 - `brands/`/`core/`/`tools/`/`hybrid_engine/`/
`gui/`/`tests/`/`datasets/`/`docs/`). 전체 디렉토리 지도 + "무엇을
하려면 어디를 읽어야 하는지" 표는 [docs/START_HERE.md](docs/START_HERE.md)
참고.
```

### 2. New `docs/START_HERE.md` + `docs/START_HERE.en.md`

Bilingual pair per `docs/CLAUDE.md`. Two tables: a directory map, and a
goal-based lookup. `core/` has no `CLAUDE.md` of its own (confirmed via
`find . -maxdepth 2 -iname CLAUDE.md` — only `brands/`, `datasets/`,
`docs/`, `gui/`, `hybrid_engine/`, `tests/`, `tools/`, plus root, have
one), so its row points to `brands/CLAUDE.md` instead of a nonexistent
file.

`docs/START_HERE.md` (Korean), full content:

```markdown
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

전체 목록은 루트 [CLAUDE.md](../CLAUDE.md)의 "## Never" 참고. 가장
중요한 것: `brands/hasselblad.py`의 `apply_hncs()`와 다른 shipped
`apply_*` 함수, `hybrid_engine/assets/profiles/*.json`/`*.dcp`는 연구
스크립트가 자동으로 덮어쓰지 않는다.
```

`docs/START_HERE.en.md` (English), full content:

```markdown
# Start Here

*[한국어](START_HERE.md)*

Back to the [main README](../README.md).

Read the root [README](../README.md)'s TL;DR first to see what this
project does. This doc only covers "where to read next" — the actual
code/methodology content lives in each directory's `CLAUDE.md` and in
`docs/methodology.en.md`.

## Directory map

| Directory | What it does | Rules doc |
|---|---|---|
| `brands/` | Per-brand color-approximation functions (`apply_*`) - the actual shipped artifact | [brands/CLAUDE.md](../brands/CLAUDE.md) |
| `core/` | Tone-curve/LUT/stats/validation helpers shared by `brands/*.py` | No dedicated doc - covered in [brands/CLAUDE.md](../brands/CLAUDE.md) |
| `tools/` | CLIs + research `evaluate_*.py` experiment scripts | [tools/CLAUDE.md](../tools/CLAUDE.md) |
| `hybrid_engine/` | Cross-camera color conversion + calibration/evaluation engine, `EVALUATION.md` (the measurement record) | [hybrid_engine/CLAUDE.md](../hybrid_engine/CLAUDE.md) |
| `gui/` | Tkinter desktop app - wraps the existing CLIs only | [gui/CLAUDE.md](../gui/CLAUDE.md) |
| `tests/` | `unittest` test suite | [tests/CLAUDE.md](../tests/CLAUDE.md) |
| `datasets/` | Committed reference CSV/JSON (official sample metadata, signature-analysis results) | [datasets/CLAUDE.md](../datasets/CLAUDE.md) |
| `docs/` | This directory - detailed documentation | [docs/CLAUDE.md](CLAUDE.md) |

## Want to do X → read Y

| Goal | Read first |
|---|---|
| Add a new brand | [docs/methodology.en.md](methodology.en.md) + [brands/CLAUDE.md](../brands/CLAUDE.md) + copy an existing population-fit brand file (e.g. `brands/nikon.py`) as a template |
| Write/run a research experiment | [tools/CLAUDE.md](../tools/CLAUDE.md) - `evaluate_*.py` conventions (standalone, statistics via `summarize()`) |
| Understand the significance/CI verdict rules | [hybrid_engine/CLAUDE.md](../hybrid_engine/CLAUDE.md)'s "Statistics — non-negotiable" |
| Add/change a GUI tab | [gui/CLAUDE.md](../gui/CLAUDE.md) |
| Edit docs (bilingual pairs etc.) | [docs/CLAUDE.md](CLAUDE.md) |
| Write a test | [tests/CLAUDE.md](../tests/CLAUDE.md) - CI has no image data |
| Add a new dataset/sample | [datasets/CLAUDE.md](../datasets/CLAUDE.md) |
| Find where a specific file lives | [docs/project_structure.en.md](project_structure.en.md) - full file index |

## Absolute rules (summary)

Full list in the root [CLAUDE.md](../CLAUDE.md)'s "## Never" section. The
most important one: `apply_hncs()` in `brands/hasselblad.py`, every other
shipped `apply_*`, and `hybrid_engine/assets/profiles/*.json`/`*.dcp`
never get auto-overwritten by a research script.
```

## Files touched

- Modify: `README.md`, `README.ko.md` (new section each)
- Create: `docs/START_HERE.md`, `docs/START_HERE.en.md`

## Verification

- Manual: every relative link in both new files resolves to a file that
  exists (`brands/CLAUDE.md`, `datasets/CLAUDE.md`, etc. all confirmed to
  exist during brainstorming).
- `python3 -m unittest discover -s tests` stays green (docs-only change,
  no test impact expected, but the project runs the full suite before
  every commit regardless).
