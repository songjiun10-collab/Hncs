# Experiments Verdict Index — Design

> Sub-project 3 of 4 in the "레포 전체 대규모 리팩토링" initiative
> (maintainability + readability). Sub-project 4 (splitting
> `tools/calibrate.py`) is the last one.

## Problem

`tools/` has 22 `evaluate_*.py` research scripts. Each one investigated
whether some candidate change would improve a shipped `brands/*.py`
function. Whether a given script's finding was **adopted**, **rejected**,
**inconclusive**, or is **reference-only** (a measurement/confirmation
step, not a decision of its own) is currently only discoverable by
reading each script's docstring and cross-referencing
`hybrid_engine/EVALUATION.md` / `docs/measurements.md` / the current
`brands/*.py` values — there is no single place that says "here's what
happened to each experiment."

## Research performed

A dedicated research pass (Explore agent) read all 22 docstrings,
cross-checked each against the current live values in the `brands/*.py`
file it targeted, and searched `hybrid_engine/EVALUATION.md` +
`docs/measurements.md` for a documented verdict. Two claims were
independently spot-checked afterward and confirmed exact
(`evaluate_x2dii_de00_grid.py`'s shipped values against
`brands/hasselblad_x2dii.py`, already read directly in this session; and
`evaluate_sony_body_split.py`'s "채택: 없음" against
`hybrid_engine/EVALUATION.md:2118` verbatim). The full research findings,
including two explicitly flagged low-confidence items, are folded into
the table below.

## Design

### Four-tag scheme

- **[채택]** (ADOPTED) — the experiment's finding is what's actually
  shipped today.
- **[기각]** (REJECTED) — tried, found not to help (or actively hurt),
  not shipped. Includes cases where a value was briefly adopted and
  later reversed by a follow-up re-verification — the *current* state is
  rejected, and the one-line summary says so.
- **[판정보류]** (INCONCLUSIVE) — bootstrap CI includes zero / sign test
  not significant; genuinely undetermined, not a loss.
- **[참고자료]** (REFERENCE-ONLY) — not a decision-making experiment:
  either a pure re-measurement/confirmation step, or (in one case) a
  script whose original premise turned out to be a no-op (Fuji demosaic)
  so the "result" is methodological, not adopt/reject.

### Three deliverables

1. **New `docs/experiments_index.md` + `.en.md`** — the master table
   (22 rows), with columns File | Verdict | Summary | Documented at.
2. **`docs/project_structure.md`/`.en.md`** — append the tag (just the
   tag, e.g. `[채택]`/`[기각]`/`[판정보류]`/`[참고자료]`, in Korean in
   both language versions since it's a fixed enum, not prose) to the
   front of each of the 22 existing `tools/evaluate_*.py` row
   descriptions.
3. **Each of the 22 `tools/evaluate_*.py` files** — add one line at the
   very top of the module docstring (the first line, before the existing
   description) with the tag and a link to the master index, e.g.:
   ```
   """[채택] - 전체 판정표는 docs/experiments_index.md 참고.

   (기존 독스트링 내용 그대로 이어짐)
   """
   ```

### Master table (source of truth for all three deliverables)

| File | Tag | Summary | Documented at |
|---|---|---|---|
| `evaluate_chromatic_aberration.py` | [기각] | rawpy `chromatic_aberration` 보정 완전 무효과 - LOO 최적 콤보가 94/94 폴드 전부 (1.0,1.0)="보정 없음", 개선폭 0.000% | `docs/measurements.md:808` |
| `evaluate_darktable_vs_rawpy.py` | [기각] | darktable-cli가 rawpy에 짐 - 평균 ΔE 4.665 vs 4.865(16쌍, 14승2패, p=0.0042), 디코더 그대로 유지 | `hybrid_engine/EVALUATION.md:1248` |
| `evaluate_exposure_gamma_x2dii.py` | [기각] | candidate(toe_lift=0.005, exposure_gamma=0.7)가 X2D II에선 이겼지만(+24.8%) CFV/X2D에서 크게 짐(p<0.001) - "폐기됨"으로 명시, 이후 0.3→0.6으로 재대체 | `docs/measurements.md:1007`; `brands/hasselblad_x2dii.py` docstring |
| `evaluate_fuji_demosaic.py` | [참고자료] | LibRaw가 X-Trans에서 AHD/DHT/AAHD를 전부 같은 Markesteijn 경로로 합쳐서 "기본 vs DHT" 비교 자체가 무의미함을 발견 - 채택/기각이 아니라 방법론적 재해석 | `hybrid_engine/EVALUATION.md:1141` |
| `evaluate_full_pixel_de00_confirm.py` | [참고자료] | 원본 해상도 재확인 도구 - X2D II 재확인에서 핵심 null 결과 발견(percentile RMSE 기준 "44.1% 개선"이 실제 ΔE00으론 -5.13%, CI가 0 포함) - 이 발견이 x2dii_de00_grid.py 재작업을 촉발함 | `docs/measurements.md:1182` |
| `evaluate_hasselblad_body_de00_grid.py` | [채택] | X1D-50c 전용 그리드서치 +6.69%(LOO), 20/20 폴드 만장일치로 shipped `apply_hncs_x1d50c`와 정확히 일치(p=0.0026) | `docs/measurements.md:1220`; `brands/hasselblad_x1d50c.py` |
| `evaluate_hncs_blend.py` | [판정보류] | 연속 블렌딩(RB/CCT) vs 하드클러스터, 74쌍에서 부호검정 p=0.908, CI [-0.013,+0.025] 0 포함 - 13쌍 때와 같은 결론 | `hybrid_engine/EVALUATION.md:1637` |
| `evaluate_hncs_structural.py` | [판정보류] | HNCS 4단계 구조 미러링 vs `apply_hncs()`, 13쌍 결과 "판정 보류(무승부)" - 4.1% 평균개선이지만 CI [-15.8%,+22.9%] 0 포함, 부호검정 p=1.000 | `hybrid_engine/EVALUATION.md:975` |
| `evaluate_leica_de00_grid.py` | [채택] | Leica SL3-P/Q3 43 그리드서치, 두 바디 다 `toe_lift=0.0, shoulder_start=0.82, white_point=1.0`로 수렴 - shipped `brands/leica_raw.py`와 정확히 일치 | `brands/leica_raw.py` docstring |
| `evaluate_native_pixel_confirm.py` | [채택] | 원본 해상도(max_dim=3000) 재확인 - X1D-50c/Leica SL2·M10/Fuji Provia 전부 shipped 값과 일치 확인(다운샘플 왜곡 없음) | `docs/measurements.md:1226,1250,1282` |
| `evaluate_new_body_de00_grid.py` | [채택] | 범용 그리드서치 CLI - Leica SL2/M10, Fuji GFX100RF/X-T30 III Provia는 채택(shipped); Canon EOS R6 III/Sony a7R VI는 유의하지만 미미해 이번엔 미채택 | `docs/measurements.md:1220-1296` |
| `evaluate_sony_a7v_de00.py` | [기각] | RMSE 튜닝 candidate가 실제 ΔE00으론 짐(-1.02%~-1.12%, p<0.0001) - percentile RMSE 목적함수 자체의 결함을 처음 노출 | `brands/sony_a7v.py` docstring |
| `evaluate_sony_a7v_de00_grid.py` | [채택] | ΔE00 직접 목적함수 재그리드서치, `toe_lift=0.06, shoulder_start=0.82, white_point=1.0` +0.53%(p<0.0001) - shipped 값과 정확히 일치 | `brands/sony_a7v.py` docstring |
| `evaluate_sony_a7v_grid_search.py` | [기각] | 첫 raw+jpeg 캘리브레이션(percentile RMSE 목적함수) - 이후 evaluate_sony_a7v_de00.py가 이 결과가 ΔE00 기준으론 오히려 나쁨을 보여 대체됨 | `brands/sony_a7v.py` docstring |
| `evaluate_sony_body_split.py` | [기각] | 바디별 vs pooled 타깃 LOO - 5바디 중 어느 하나도 b2/w995 둘 다 유의하게 못 이김, "채택: 없음" 명시 | `hybrid_engine/EVALUATION.md:2118` |
| `evaluate_x2dii_color_matrix.py` | [기각] | X2D II 41장 자체로 3x3 매트릭스 재피팅해도 톤커브 단독보다 나쁨(-13.9%, CI 전부 음수) | `docs/measurements.md:1125` |
| `evaluate_x2dii_combined.py` | [기각] | 분리감마+채도/hue 조합("콤보 A/B") - 당시 미채택 상태였던 베이스라인(exposure_gamma=0.3) 위에 지어졌고 그 베이스라인 자체가 나중에 기각됨 - shipped 코드에 해당 단계 없음 | 커밋 83e63d8; `core/engine.py`(make_hasselblad_body_look에 분리감마/LUT 파라미터 없음)로 교차확인 |
| `evaluate_x2dii_combo_a_full.py` | [기각] | 콤보 A 전체지표(ΔE00+RMSE+drop-one) 재확인 - 위와 같은 이유로 미채택, shipped 코드에 분리감마 단계 없음 | 커밋 83e63d8; `brands/hasselblad_x2dii.py`로 교차확인 |
| `evaluate_x2dii_de00_check.py` | [참고자료] | shoulder_start 정정(0.82->0.5) 이후 70쌍 전체로 ΔE00/RMSE 재확인만 하는 순수 체크포인트, 자체 채택/기각 판정 없음 | 파일 자체 독스트링 |
| `evaluate_x2dii_de00_grid.py` | [채택] | ΔE00 직접 목적함수 441콤보 그리드서치 - `exposure_gamma=0.6, toe_lift=0.02, shoulder_start=0.58, white_point=0.95`, +12.99%(61승9패, CI [+1.421,+2.065] 0 미포함) - shipped 값과 정확히 일치, percentile RMSE 기준 이전 결과를 대체 | `docs/measurements.md:1182-1218`; `brands/hasselblad_x2dii.py` |
| `evaluate_x2dii_generation_loo.py` | [기각] | percentile RMSE 기준 X2D II 전용 그리드서치(41→70쌍 확장, shoulder_start 0.82→0.5) - 한때 채택됐다가 ΔE00 직접비교(evaluate_full_pixel_de00_confirm.py)에서 CI가 0 포함으로 나와 최종 기각, 현재 값은 evaluate_x2dii_de00_grid.py에서 옴 | `docs/measurements.md:1052,1095`; 대체 근거는 `1182-1218` |
| `evaluate_x2dii_reduce_de00.py` | [기각] | 학습LUT/분리감마/채도-hue 세 후보 - 도입 커밋에서부터 "시각 검증 대기 중 미채택"으로 명시, 이후 베이스라인 자체가 재작업되며 셋 다 shipped 코드에 없음 | 커밋 83e63d8; `brands/hasselblad_x2dii.py`로 교차확인 |

**Confidence notes** (from the research pass, kept here for the record —
not shown in the published index): `evaluate_hncs_structural.py`'s
[판정보류] tag rests on the original 13-pair verdict in
`EVALUATION.md`; the doc itself admits its 95-pair local rerun was never
written up as its own head-to-head table there. `evaluate_x2dii_combined.py`,
`evaluate_x2dii_combo_a_full.py`, and `evaluate_x2dii_reduce_de00.py` have
no dedicated `EVALUATION.md`/`measurements.md` section — their [기각] tag
is inferred from the introducing commit message plus direct confirmation
that no split-gamma/learned-LUT/chroma stage exists in shipped
`brands/hasselblad_x2dii.py`/`core/engine.py`, not from an explicit "기각"
sentence in the docs. Both are solid conclusions but worth a human's
awareness if a future re-audit disagrees.

## Non-goals

- Not re-litigating any verdict — this sub-project only records what
  already happened, per the research above. If a tag looks wrong to the
  user on review, that's a correction to make before implementation, not
  during it.
- Not touching any `brands/*.py` file, any shipped `apply_*` function, or
  any test file — this is docs + docstring-comment-only.
- Not tagging the other 24 `tools/*.py` files that aren't
  `evaluate_*.py` experiments (e.g. `analyze.py`, `calibrate.py`,
  `download.py`) — those aren't "did this idea win or lose" experiments,
  they're CLIs/infrastructure, out of scope for a verdict tag.

## Files touched

- Create: `docs/experiments_index.md`, `docs/experiments_index.en.md`
- Modify: `docs/project_structure.md`, `docs/project_structure.en.md`
  (22 rows each get a tag prepended)
- Modify: all 22 `tools/evaluate_*.py` files (one new docstring line each)

## Verification

- Every relative link in the two new index docs resolves (same
  link-check pattern as the sub-project 1 onboarding docs).
- `python3 -m unittest discover -s tests` stays green — this change adds
  a docstring line and doc content only; no test should be affected, but
  the project always confirms the full suite before every commit
  regardless.
- Spot-check: `grep -c "^\[" ...` or equivalent confirms all 22 files got
  exactly one tag line, no duplicates.
