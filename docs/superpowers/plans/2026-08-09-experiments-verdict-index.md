# Experiments Verdict Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every one of the 22 `tools/evaluate_*.py` research scripts
a visible, consistent verdict tag ([채택]/[기각]/[판정보류]/[참고자료]) in
three places: a new master index doc, `docs/project_structure.md`'s
existing rows, and each script's own docstring.

**Architecture:** Pure documentation + docstring-comment change, zero
logic touched. Three independent deliverables, each its own task: (1)
the new bilingual index doc, (2) the 22 docstring tag lines, (3) the 22
`project_structure.md`/`.en.md` row tags.

**Tech Stack:** Markdown, Python docstrings (text only).

## Global Constraints

- No `brands/*.py` file, shipped `apply_*` function, or test file is
  touched by this plan — verify this explicitly at the end.
- Bilingual parity mandatory (`docs/CLAUDE.md`): the new index doc and
  the `project_structure.md` edits both need Korean + English versions.
- The tag scheme is fixed: `[채택]` (adopted), `[기각]` (rejected,
  including "adopted then later reversed"), `[판정보류]` (inconclusive,
  CI includes zero), `[참고자료]` (reference-only measurement/confirmation
  step, not a decision).
- `python3 -m unittest discover -s tests` must stay green (excluding the
  sandbox's pre-existing, unrelated `torch`/`tkinter` import errors).
- Master verdict table (all three tasks pull from this — reproduced here
  so no task needs to re-derive it):

| File | Tag | Summary (Korean) | Summary (English) | Documented at |
|---|---|---|---|---|
| `evaluate_chromatic_aberration.py` | 기각 | rawpy `chromatic_aberration` 보정 완전 무효과 - LOO 최적 콤보가 94/94 폴드 전부 (1.0,1.0)="보정 없음", 개선폭 0.000% | rawpy's `chromatic_aberration` correction has zero effect — the LOO-optimal combo was (1.0,1.0) ("no correction") in 94/94 folds, 0.000% improvement | `docs/measurements.md:808` |
| `evaluate_darktable_vs_rawpy.py` | 기각 | darktable-cli가 rawpy에 짐 - 평균 ΔE 4.665 vs 4.865(16쌍, 14승2패, p=0.0042), 디코더 그대로 유지 | darktable-cli loses to rawpy — mean ΔE 4.665 vs 4.865 (16 pairs, 14W/2L, p=0.0042); decoder unchanged | `hybrid_engine/EVALUATION.md:1248` |
| `evaluate_exposure_gamma_x2dii.py` | 기각 | candidate(toe_lift=0.005, exposure_gamma=0.7)가 X2D II에선 이겼지만(+24.8%) CFV/X2D에서 크게 짐(p<0.001) - "폐기됨"으로 명시, 이후 0.3→0.6으로 재대체 | the candidate (toe_lift=0.005, exposure_gamma=0.7) won on X2D II (+24.8%) but lost badly on CFV/X2D (p<0.001) — explicitly discarded, later replaced by 0.3 then 0.6 | `docs/measurements.md:1007`; `brands/hasselblad_x2dii.py` docstring |
| `evaluate_fuji_demosaic.py` | 참고자료 | LibRaw가 X-Trans에서 AHD/DHT/AAHD를 전부 같은 Markesteijn 경로로 합쳐서 "기본 vs DHT" 비교 자체가 무의미함을 발견 - 채택/기각이 아니라 방법론적 재해석 | discovered LibRaw collapses AHD/DHT/AAHD onto the same Markesteijn path for X-Trans, making "default vs DHT" a no-op comparison — a methodological finding, not an adopt/reject decision | `hybrid_engine/EVALUATION.md:1141` |
| `evaluate_full_pixel_de00_confirm.py` | 참고자료 | 원본 해상도 재확인 도구 - X2D II 재확인에서 핵심 null 결과 발견(percentile RMSE 기준 "44.1% 개선"이 실제 ΔE00으론 -5.13%, CI가 0 포함) - 이 발견이 x2dii_de00_grid.py 재작업을 촉발함 | native-resolution confirmation tool — its X2D II recheck found a pivotal null result (the percentile-RMSE-based "44.1% improvement" was actually -5.13% in real ΔE00, CI includes zero), triggering the x2dii_de00_grid.py rework | `docs/measurements.md:1182` |
| `evaluate_hasselblad_body_de00_grid.py` | 채택 | X1D-50c 전용 그리드서치 +6.69%(LOO), 20/20 폴드 만장일치로 shipped `apply_hncs_x1d50c`와 정확히 일치(p=0.0026) | X1D-50c-specific grid search, +6.69% (LOO), 20/20 folds unanimous, matches shipped `apply_hncs_x1d50c` exactly (p=0.0026) | `docs/measurements.md:1220`; `brands/hasselblad_x1d50c.py` |
| `evaluate_hncs_blend.py` | 판정보류 | 연속 블렌딩(RB/CCT) vs 하드클러스터, 74쌍에서 부호검정 p=0.908, CI [-0.013,+0.025] 0 포함 - 13쌍 때와 같은 결론 | continuous blending (RB/CCT) vs hard clustering, 74 pairs: sign-test p=0.908, CI [-0.013,+0.025] includes zero — same conclusion as the original 13-pair run | `hybrid_engine/EVALUATION.md:1637` |
| `evaluate_hncs_structural.py` | 판정보류 | HNCS 4단계 구조 미러링 vs `apply_hncs()`, 13쌍 결과 "판정 보류(무승부)" - 4.1% 평균개선이지만 CI [-15.8%,+22.9%] 0 포함, 부호검정 p=1.000 | mirroring HNCS's real 4-stage pipeline vs `apply_hncs()`, 13 pairs: "inconclusive (tie)" — 4.1% mean improvement but CI [-15.8%,+22.9%] includes zero, sign-test p=1.000 | `hybrid_engine/EVALUATION.md:975` |
| `evaluate_leica_de00_grid.py` | 채택 | Leica SL3-P/Q3 43 그리드서치, 두 바디 다 `toe_lift=0.0, shoulder_start=0.82, white_point=1.0`로 수렴 - shipped `brands/leica_raw.py`와 정확히 일치 | Leica SL3-P/Q3 43 grid search — both bodies converge on `toe_lift=0.0, shoulder_start=0.82, white_point=1.0`, matching shipped `brands/leica_raw.py` exactly | `brands/leica_raw.py` docstring |
| `evaluate_native_pixel_confirm.py` | 채택 | 원본 해상도(max_dim=3000) 재확인 - X1D-50c/Leica SL2·M10/Fuji Provia 전부 shipped 값과 일치 확인(다운샘플 왜곡 없음) | native-resolution (max_dim=3000) reconfirmation — X1D-50c/Leica SL2·M10/Fuji Provia all match shipped values (no downsampling distortion) | `docs/measurements.md:1226,1250,1282` |
| `evaluate_new_body_de00_grid.py` | 채택 | 범용 그리드서치 CLI - Leica SL2/M10, Fuji GFX100RF/X-T30 III Provia는 채택(shipped); Canon EOS R6 III/Sony a7R VI는 유의하지만 미미해 이번엔 미채택 | generic grid-search CLI — Leica SL2/M10 and Fuji GFX100RF/X-T30 III Provia were adopted (shipped); Canon EOS R6 III/Sony a7R VI were statistically significant but too small to adopt this round | `docs/measurements.md:1220-1296` |
| `evaluate_sony_a7v_de00.py` | 기각 | RMSE 튜닝 candidate가 실제 ΔE00으론 짐(-1.02%~-1.12%, p<0.0001) - percentile RMSE 목적함수 자체의 결함을 처음 노출 | the RMSE-tuned candidate actually loses on real ΔE00 (-1.02% to -1.12%, p<0.0001) — first exposed the flaw in using percentile RMSE as the objective | `brands/sony_a7v.py` docstring |
| `evaluate_sony_a7v_de00_grid.py` | 채택 | ΔE00 직접 목적함수 재그리드서치, `toe_lift=0.06, shoulder_start=0.82, white_point=1.0` +0.53%(p<0.0001) - shipped 값과 정확히 일치 | re-grid-search with ΔE00 as the direct objective — `toe_lift=0.06, shoulder_start=0.82, white_point=1.0`, +0.53% (p<0.0001), matches shipped values exactly | `brands/sony_a7v.py` docstring |
| `evaluate_sony_a7v_grid_search.py` | 기각 | 첫 raw+jpeg 캘리브레이션(percentile RMSE 목적함수) - 이후 evaluate_sony_a7v_de00.py가 이 결과가 ΔE00 기준으론 오히려 나쁨을 보여 대체됨 | the first raw+jpeg calibration (percentile-RMSE objective) — later superseded once evaluate_sony_a7v_de00.py showed it was actually worse on real ΔE00 | `brands/sony_a7v.py` docstring |
| `evaluate_sony_body_split.py` | 기각 | 바디별 vs pooled 타깃 LOO - 5바디 중 어느 하나도 b2/w995 둘 다 유의하게 못 이김, "채택: 없음" 명시 | per-body vs pooled-target LOO — none of the 5 bodies won significantly on both b2 and w995; explicitly "adopted: none" | `hybrid_engine/EVALUATION.md:2118` |
| `evaluate_x2dii_color_matrix.py` | 기각 | X2D II 41장 자체로 3x3 매트릭스 재피팅해도 톤커브 단독보다 나쁨(-13.9%, CI 전부 음수) | refitting a 3x3 matrix on the 41 real X2D II photos themselves still loses to tone-curve-only (-13.9%, CI fully negative) | `docs/measurements.md:1125` |
| `evaluate_x2dii_combined.py` | 기각 | 분리감마+채도/hue 조합("콤보 A/B") - 당시 미채택 상태였던 베이스라인(exposure_gamma=0.3) 위에 지어졌고 그 베이스라인 자체가 나중에 기각됨 - shipped 코드에 해당 단계 없음 | split-gamma + saturation/hue combos ("combo A/B") — built on a since-rejected baseline (exposure_gamma=0.3); no such stage exists in shipped code | commit `83e63d8`; cross-checked against `core/engine.py` (no split-gamma/LUT params in `make_hasselblad_body_look`) |
| `evaluate_x2dii_combo_a_full.py` | 기각 | 콤보 A 전체지표(ΔE00+RMSE+drop-one) 재확인 - 위와 같은 이유로 미채택, shipped 코드에 분리감마 단계 없음 | full-metrics recheck of combo A (ΔE00+RMSE+drop-one) — same reason as above, no split-gamma stage in shipped code | commit `83e63d8`; cross-checked against `brands/hasselblad_x2dii.py` |
| `evaluate_x2dii_de00_check.py` | 참고자료 | shoulder_start 정정(0.82->0.5) 이후 70쌍 전체로 ΔE00/RMSE 재확인만 하는 순수 체크포인트, 자체 채택/기각 판정 없음 | a pure checkpoint re-confirming ΔE00/RMSE on the full 70-pair set after the shoulder_start correction (0.82→0.5) — no adopt/reject decision of its own | script's own docstring |
| `evaluate_x2dii_de00_grid.py` | 채택 | ΔE00 직접 목적함수 441콤보 그리드서치 - `exposure_gamma=0.6, toe_lift=0.02, shoulder_start=0.58, white_point=0.95`, +12.99%(61승9패, CI [+1.421,+2.065] 0 미포함) - shipped 값과 정확히 일치, percentile RMSE 기준 이전 결과를 대체 | 441-combo grid search with ΔE00 as the direct objective — `exposure_gamma=0.6, toe_lift=0.02, shoulder_start=0.58, white_point=0.95`, +12.99% (61W/9L, CI [+1.421,+2.065] excludes zero), matches shipped values, supersedes the earlier percentile-RMSE result | `docs/measurements.md:1182-1218`; `brands/hasselblad_x2dii.py` |
| `evaluate_x2dii_generation_loo.py` | 기각 | percentile RMSE 기준 X2D II 전용 그리드서치(41→70쌍 확장, shoulder_start 0.82→0.5) - 한때 채택됐다가 ΔE00 직접비교(evaluate_full_pixel_de00_confirm.py)에서 CI가 0 포함으로 나와 최종 기각, 현재 값은 evaluate_x2dii_de00_grid.py에서 옴 | percentile-RMSE-objective X2D II-only grid search (41→70 pairs, shoulder_start 0.82→0.5) — briefly adopted, then finally rejected once direct ΔE00 comparison showed CI including zero; current values come from evaluate_x2dii_de00_grid.py instead | `docs/measurements.md:1052,1095`; superseded per `1182-1218` |
| `evaluate_x2dii_reduce_de00.py` | 기각 | 학습LUT/분리감마/채도-hue 세 후보 - 도입 커밋에서부터 "시각 검증 대기 중 미채택"으로 명시, 이후 베이스라인 자체가 재작업되며 셋 다 shipped 코드에 없음 | three candidates (learned LUT/split-gamma/saturation-hue) — explicitly "not yet adopted pending visual verification" from the introducing commit; none exist in shipped code after the baseline itself was reworked | commit `83e63d8`; cross-checked against `brands/hasselblad_x2dii.py` |

---

### Task 1: Create `docs/experiments_index.md` + `docs/experiments_index.en.md`

**Files:**
- Create: `docs/experiments_index.md`
- Create: `docs/experiments_index.en.md`

**Interfaces:**
- Consumes: nothing (no code dependencies).
- Produces: two files that Tasks 2 and 3 can link to (already referenced
  by name — `docs/experiments_index.md`/`.en.md` — in the docstring tag
  line Task 2 adds).

- [ ] **Step 1: Create `docs/experiments_index.md` with this exact content**

```markdown
# 실험 판정표

*[English](experiments_index.en.md)*

[메인 README](../README.ko.md)로 돌아가기.

`tools/evaluate_*.py` 연구 스크립트 22개가 각각 어떤 브랜드 값을
검증했고 그 결과가 실제로 채택됐는지 정리한 표. 태그 4종:

- **[채택]** - 이 실험의 결론이 실제로 shipped 코드에 반영됨
- **[기각]** - 시도했으나 도움 안 됨(혹은 해로움), 미채택. 한때
  채택됐다가 후속 재검증으로 뒤집힌 경우도 포함(최종 상태 기준)
- **[판정보류]** - 부트스트랩 CI가 0을 포함/부호검정 유의성 없음 - 이긴
  것도 진 것도 아님
- **[참고자료]** - 채택/기각을 가리는 실험이 아니라 순수 재확인/체크포인트,
  또는 원래 전제 자체가 무효화된 경우

각 스크립트 자체의 독스트링 첫 줄에도 같은 태그가 있다.
`docs/project_structure.md`의 해당 파일 행에도 표시돼 있다.

| 파일 | 판정 | 요약 | 근거 |
|---|---|---|---|
| `tools/evaluate_chromatic_aberration.py` | [기각] | rawpy `chromatic_aberration` 보정 완전 무효과 - LOO 최적 콤보가 94/94 폴드 전부 (1.0,1.0)="보정 없음", 개선폭 0.000% | `docs/measurements.md:808` |
| `tools/evaluate_darktable_vs_rawpy.py` | [기각] | darktable-cli가 rawpy에 짐 - 평균 ΔE 4.665 vs 4.865(16쌍, 14승2패, p=0.0042), 디코더 그대로 유지 | `hybrid_engine/EVALUATION.md:1248` |
| `tools/evaluate_exposure_gamma_x2dii.py` | [기각] | candidate(toe_lift=0.005, exposure_gamma=0.7)가 X2D II에선 이겼지만(+24.8%) CFV/X2D에서 크게 짐(p<0.001) - "폐기됨"으로 명시, 이후 0.3→0.6으로 재대체 | `docs/measurements.md:1007`; `brands/hasselblad_x2dii.py` |
| `tools/evaluate_fuji_demosaic.py` | [참고자료] | LibRaw가 X-Trans에서 AHD/DHT/AAHD를 전부 같은 Markesteijn 경로로 합쳐서 "기본 vs DHT" 비교 자체가 무의미함을 발견 - 방법론적 재해석 | `hybrid_engine/EVALUATION.md:1141` |
| `tools/evaluate_full_pixel_de00_confirm.py` | [참고자료] | 원본 해상도 재확인 도구 - X2D II 재확인에서 핵심 null 결과 발견(percentile RMSE 기준 "44.1% 개선"이 실제 ΔE00으론 -5.13%, CI 0 포함) | `docs/measurements.md:1182` |
| `tools/evaluate_hasselblad_body_de00_grid.py` | [채택] | X1D-50c 전용 그리드서치 +6.69%(LOO), 20/20 폴드 만장일치로 shipped `apply_hncs_x1d50c`와 정확히 일치(p=0.0026) | `docs/measurements.md:1220`; `brands/hasselblad_x1d50c.py` |
| `tools/evaluate_hncs_blend.py` | [판정보류] | 연속 블렌딩(RB/CCT) vs 하드클러스터, 74쌍에서 부호검정 p=0.908, CI [-0.013,+0.025] 0 포함 | `hybrid_engine/EVALUATION.md:1637` |
| `tools/evaluate_hncs_structural.py` | [판정보류] | HNCS 4단계 구조 미러링 vs `apply_hncs()`, 13쌍 결과 "판정 보류(무승부)" - CI [-15.8%,+22.9%] 0 포함 | `hybrid_engine/EVALUATION.md:975` |
| `tools/evaluate_leica_de00_grid.py` | [채택] | Leica SL3-P/Q3 43 그리드서치, 두 바디 다 `toe_lift=0.0, shoulder_start=0.82, white_point=1.0`로 수렴 - shipped `brands/leica_raw.py`와 일치 | `brands/leica_raw.py` |
| `tools/evaluate_native_pixel_confirm.py` | [채택] | 원본 해상도(max_dim=3000) 재확인 - X1D-50c/Leica SL2·M10/Fuji Provia 전부 shipped 값과 일치 확인 | `docs/measurements.md:1226,1250,1282` |
| `tools/evaluate_new_body_de00_grid.py` | [채택] | 범용 그리드서치 CLI - Leica SL2/M10, Fuji GFX100RF/X-T30 III Provia 채택; Canon EOS R6 III/Sony a7R VI는 이번엔 미채택 | `docs/measurements.md:1220-1296` |
| `tools/evaluate_sony_a7v_de00.py` | [기각] | RMSE 튜닝 candidate가 실제 ΔE00으론 짐(-1.02%~-1.12%, p<0.0001) - percentile RMSE 목적함수 결함을 처음 노출 | `brands/sony_a7v.py` |
| `tools/evaluate_sony_a7v_de00_grid.py` | [채택] | ΔE00 직접 목적함수 재그리드서치, `toe_lift=0.06, shoulder_start=0.82, white_point=1.0` +0.53%(p<0.0001) - shipped 값과 일치 | `brands/sony_a7v.py` |
| `tools/evaluate_sony_a7v_grid_search.py` | [기각] | 첫 raw+jpeg 캘리브레이션(percentile RMSE) - 이후 evaluate_sony_a7v_de00.py가 ΔE00 기준으론 나쁨을 보여 대체됨 | `brands/sony_a7v.py` |
| `tools/evaluate_sony_body_split.py` | [기각] | 바디별 vs pooled 타깃 LOO - 5바디 중 어느 하나도 b2/w995 둘 다 유의하게 못 이김, "채택: 없음" 명시 | `hybrid_engine/EVALUATION.md:2118` |
| `tools/evaluate_x2dii_color_matrix.py` | [기각] | X2D II 41장 자체로 3x3 매트릭스 재피팅해도 톤커브 단독보다 나쁨(-13.9%, CI 전부 음수) | `docs/measurements.md:1125` |
| `tools/evaluate_x2dii_combined.py` | [기각] | 분리감마+채도/hue 조합("콤보 A/B") - 이후 기각된 베이스라인 위에 지어졌음, shipped 코드에 해당 단계 없음 | 커밋 `83e63d8`; `core/engine.py` |
| `tools/evaluate_x2dii_combo_a_full.py` | [기각] | 콤보 A 전체지표 재확인 - 위와 같은 이유로 미채택 | 커밋 `83e63d8`; `brands/hasselblad_x2dii.py` |
| `tools/evaluate_x2dii_de00_check.py` | [참고자료] | shoulder_start 정정(0.82->0.5) 이후 70쌍 전체 ΔE00/RMSE 재확인 체크포인트, 자체 판정 없음 | 파일 자체 독스트링 |
| `tools/evaluate_x2dii_de00_grid.py` | [채택] | ΔE00 직접 목적함수 441콤보 그리드서치 - `exposure_gamma=0.6, toe_lift=0.02, shoulder_start=0.58, white_point=0.95`, +12.99%(CI [+1.421,+2.065]) - shipped 값과 일치 | `docs/measurements.md:1182-1218`; `brands/hasselblad_x2dii.py` |
| `tools/evaluate_x2dii_generation_loo.py` | [기각] | percentile RMSE 기준 그리드서치(41→70쌍) - 한때 채택됐다가 ΔE00 직접비교에서 최종 기각, 현재 값은 evaluate_x2dii_de00_grid.py에서 옴 | `docs/measurements.md:1052,1095` |
| `tools/evaluate_x2dii_reduce_de00.py` | [기각] | 학습LUT/분리감마/채도-hue 세 후보 - "시각 검증 대기 중 미채택"으로 명시, 이후 베이스라인 재작업으로 셋 다 shipped 코드에 없음 | 커밋 `83e63d8`; `brands/hasselblad_x2dii.py` |
```

- [ ] **Step 2: Create `docs/experiments_index.en.md` with this exact content**

```markdown
# Experiments Verdict Index

*[한국어](experiments_index.md)*

Back to the [main README](../README.md).

A table of what each of the 22 `tools/evaluate_*.py` research scripts
tested, and whether the finding actually made it into shipped code. Four
tags:

- **[ADOPTED]** — this experiment's conclusion is what's actually shipped
- **[REJECTED]** — tried, found not to help (or actively hurt), not
  shipped. Includes cases briefly adopted then reversed by a later
  re-verification (final state, not history)
- **[INCONCLUSIVE]** — bootstrap CI includes zero / sign test not
  significant — neither a win nor a loss
- **[REFERENCE-ONLY]** — not an adopt/reject experiment: a pure
  re-measurement/checkpoint, or a case where the original premise itself
  turned out invalid

Each script's own docstring carries the same tag on its first line.
`docs/project_structure.en.md`'s row for that file shows it too.

| File | Verdict | Summary | Documented at |
|---|---|---|---|
| `tools/evaluate_chromatic_aberration.py` | [REJECTED] | rawpy's `chromatic_aberration` correction has zero effect — LOO-optimal combo was (1.0,1.0) ("no correction") in 94/94 folds, 0.000% improvement | `docs/measurements.md:808` |
| `tools/evaluate_darktable_vs_rawpy.py` | [REJECTED] | darktable-cli loses to rawpy — mean ΔE 4.665 vs 4.865 (16 pairs, 14W/2L, p=0.0042); decoder unchanged | `hybrid_engine/EVALUATION.md:1248` |
| `tools/evaluate_exposure_gamma_x2dii.py` | [REJECTED] | candidate (toe_lift=0.005, exposure_gamma=0.7) won on X2D II (+24.8%) but lost badly on CFV/X2D (p<0.001) — explicitly discarded, later replaced by 0.3 then 0.6 | `docs/measurements.md:1007`; `brands/hasselblad_x2dii.py` |
| `tools/evaluate_fuji_demosaic.py` | [REFERENCE-ONLY] | discovered LibRaw collapses AHD/DHT/AAHD onto the same Markesteijn path for X-Trans — a methodological finding, not adopt/reject | `hybrid_engine/EVALUATION.md:1141` |
| `tools/evaluate_full_pixel_de00_confirm.py` | [REFERENCE-ONLY] | native-resolution confirmation tool — its X2D II recheck found a pivotal null result (percentile-RMSE "44.1% improvement" was actually -5.13% in real ΔE00, CI includes zero) | `docs/measurements.md:1182` |
| `tools/evaluate_hasselblad_body_de00_grid.py` | [ADOPTED] | X1D-50c-specific grid search, +6.69% (LOO), 20/20 folds unanimous, matches shipped `apply_hncs_x1d50c` exactly (p=0.0026) | `docs/measurements.md:1220`; `brands/hasselblad_x1d50c.py` |
| `tools/evaluate_hncs_blend.py` | [INCONCLUSIVE] | continuous blending (RB/CCT) vs hard clustering, 74 pairs: sign-test p=0.908, CI [-0.013,+0.025] includes zero | `hybrid_engine/EVALUATION.md:1637` |
| `tools/evaluate_hncs_structural.py` | [INCONCLUSIVE] | mirroring HNCS's real 4-stage pipeline vs `apply_hncs()`, 13 pairs: "inconclusive (tie)" — CI [-15.8%,+22.9%] includes zero | `hybrid_engine/EVALUATION.md:975` |
| `tools/evaluate_leica_de00_grid.py` | [ADOPTED] | Leica SL3-P/Q3 43 grid search — both bodies converge on `toe_lift=0.0, shoulder_start=0.82, white_point=1.0`, matching shipped `brands/leica_raw.py` | `brands/leica_raw.py` |
| `tools/evaluate_native_pixel_confirm.py` | [ADOPTED] | native-resolution (max_dim=3000) reconfirmation — X1D-50c/Leica SL2·M10/Fuji Provia all match shipped values | `docs/measurements.md:1226,1250,1282` |
| `tools/evaluate_new_body_de00_grid.py` | [ADOPTED] | generic grid-search CLI — Leica SL2/M10 and Fuji GFX100RF/X-T30 III Provia adopted; Canon EOS R6 III/Sony a7R VI not adopted this round | `docs/measurements.md:1220-1296` |
| `tools/evaluate_sony_a7v_de00.py` | [REJECTED] | the RMSE-tuned candidate actually loses on real ΔE00 (-1.02% to -1.12%, p<0.0001) — first exposed the percentile-RMSE objective flaw | `brands/sony_a7v.py` |
| `tools/evaluate_sony_a7v_de00_grid.py` | [ADOPTED] | re-grid-search with ΔE00 as the direct objective — matches shipped values exactly, +0.53% (p<0.0001) | `brands/sony_a7v.py` |
| `tools/evaluate_sony_a7v_grid_search.py` | [REJECTED] | the first raw+jpeg calibration (percentile-RMSE objective) — superseded once shown to be worse on real ΔE00 | `brands/sony_a7v.py` |
| `tools/evaluate_sony_body_split.py` | [REJECTED] | per-body vs pooled-target LOO — none of the 5 bodies won significantly on both b2 and w995; explicitly "adopted: none" | `hybrid_engine/EVALUATION.md:2118` |
| `tools/evaluate_x2dii_color_matrix.py` | [REJECTED] | refitting a 3x3 matrix on the 41 real X2D II photos still loses to tone-curve-only (-13.9%, CI fully negative) | `docs/measurements.md:1125` |
| `tools/evaluate_x2dii_combined.py` | [REJECTED] | split-gamma + saturation/hue combos — built on a since-rejected baseline, no such stage in shipped code | commit `83e63d8`; `core/engine.py` |
| `tools/evaluate_x2dii_combo_a_full.py` | [REJECTED] | full-metrics recheck of combo A — same reason, no split-gamma stage in shipped code | commit `83e63d8`; `brands/hasselblad_x2dii.py` |
| `tools/evaluate_x2dii_de00_check.py` | [REFERENCE-ONLY] | a pure checkpoint re-confirming ΔE00/RMSE after the shoulder_start correction — no decision of its own | script's own docstring |
| `tools/evaluate_x2dii_de00_grid.py` | [ADOPTED] | 441-combo grid search with ΔE00 as the direct objective — matches shipped values, +12.99% (CI [+1.421,+2.065]) | `docs/measurements.md:1182-1218`; `brands/hasselblad_x2dii.py` |
| `tools/evaluate_x2dii_generation_loo.py` | [REJECTED] | percentile-RMSE-objective grid search (41→70 pairs) — briefly adopted, then finally rejected once ΔE00 CI included zero | `docs/measurements.md:1052,1095` |
| `tools/evaluate_x2dii_reduce_de00.py` | [REJECTED] | three candidates (learned LUT/split-gamma/saturation-hue) — explicitly not yet adopted pending visual verification, none exist after the baseline was reworked | commit `83e63d8`; `brands/hasselblad_x2dii.py` |
```

- [ ] **Step 3: Verify every relative link in both new files resolves**

```bash
python3 - <<'EOF'
import re, os

for path in ["docs/experiments_index.md", "docs/experiments_index.en.md"]:
    text = open(path).read()
    links = re.findall(r"\]\(([^)]+)\)", text)
    base = os.path.dirname(path)
    for link in links:
        target = os.path.normpath(os.path.join(base, link))
        assert os.path.exists(target), f"{path}: broken link -> {link} (resolved {target})"
print("all links resolve")
EOF
```

Expected: `all links resolve`

- [ ] **Step 4: Commit**

```bash
git add docs/experiments_index.md docs/experiments_index.en.md
git commit -m "Add docs/experiments_index.md(.en.md): verdict table for 22 tools/evaluate_*.py scripts"
```

---

### Task 2: Add a verdict tag to each of the 22 scripts' docstrings

**Files:**
- Modify: all 22 `tools/evaluate_*.py` files listed in the Global
  Constraints master table.

**Interfaces:**
- Consumes: nothing from Task 1 except the file names
  `docs/experiments_index.md`/`.en.md` (referenced in the tag line's
  text, not imported).
- Produces: nothing consumed by later tasks.

For each file, insert one new line as the very first line of the module
docstring (immediately after the opening `"""`), followed by a blank
line, then the file's existing content continues unchanged. The exact
tag line format is:

```
[tag] - 전체 판정표는 docs/experiments_index.md 참고.
```

(same Korean line in every file, regardless of the file's own language
mix — this project's docstrings are Korean-first throughout).

- [ ] **Step 1: `tools/evaluate_chromatic_aberration.py`**

Change:
```python
"""
색수차 보정(chromatic_aberration) 실험 - rawpy raw.postprocess()의
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

색수차 보정(chromatic_aberration) 실험 - rawpy raw.postprocess()의
```

- [ ] **Step 2: `tools/evaluate_darktable_vs_rawpy.py`**

Change:
```python
"""rawpy(decode_raw) vs darktable-cli(decode_raw_darktable) RAW 디코드
비교 - 핫셀블라드 13쌍 + Fuji 3쌍(총 16쌍) 실제 raw+jpeg 페어로 확인.
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

rawpy(decode_raw) vs darktable-cli(decode_raw_darktable) RAW 디코드
비교 - 핫셀블라드 13쌍 + Fuji 3쌍(총 16쌍) 실제 raw+jpeg 페어로 확인.
```

- [ ] **Step 3: `tools/evaluate_exposure_gamma_x2dii.py`**

Change:
```python
"""
main(origin)과 candidate(로컬 v13) 두 apply_hncs 파라미터 후보를, 둘 다
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

main(origin)과 candidate(로컬 v13) 두 apply_hncs 파라미터 후보를, 둘 다
```

- [ ] **Step 4: `tools/evaluate_fuji_demosaic.py`**

Change:
```python
"""Fuji X-Trans 데모자이크 알고리즘(rawpy 기본 vs DHT) ΔE 비교 - 로컬에
있는 실제 raw+jpeg 페어 3쌍(fuji_pairs_manifest.csv)으로 확인한다.
```
to:
```python
"""[참고자료] - 전체 판정표는 docs/experiments_index.md 참고.

Fuji X-Trans 데모자이크 알고리즘(rawpy 기본 vs DHT) ΔE 비교 - 로컬에
있는 실제 raw+jpeg 페어 3쌍(fuji_pairs_manifest.csv)으로 확인한다.
```

- [ ] **Step 5: `tools/evaluate_full_pixel_de00_confirm.py`**

Change:
```python
"""
이 프로젝트에서 확정한 모든 raw+jpeg 기반 신규 함수의 ΔE00을 - 그리드서치/
```
to:
```python
"""[참고자료] - 전체 판정표는 docs/experiments_index.md 참고.

이 프로젝트에서 확정한 모든 raw+jpeg 기반 신규 함수의 ΔE00을 - 그리드서치/
```

- [ ] **Step 6: `tools/evaluate_hasselblad_body_de00_grid.py`**

Change:
```python
"""
Hasselblad 신규/소표본 바디(X1D-50c 등) 전용 ΔE00 그리드서치 + LOO.
```
to:
```python
"""[채택] - 전체 판정표는 docs/experiments_index.md 참고.

Hasselblad 신규/소표본 바디(X1D-50c 등) 전용 ΔE00 그리드서치 + LOO.
```

- [ ] **Step 7: `tools/evaluate_hncs_blend.py`**

Change:
```python
"""HNCS 조명 블렌딩(illuminant blend) 실험 - hncs_structural.py의
하드-클러스터 구조 실험(cluster_a/cluster_b 하드 분류)을, 연속
```
to:
```python
"""[판정보류] - 전체 판정표는 docs/experiments_index.md 참고.

HNCS 조명 블렌딩(illuminant blend) 실험 - hncs_structural.py의
하드-클러스터 구조 실험(cluster_a/cluster_b 하드 분류)을, 연속
```

- [ ] **Step 8: `tools/evaluate_hncs_structural.py`**

Change:
```python
"""
HNCS 실제 4단계 구조(조명별 3x3 매트릭스 -> 조명별 chroma LUT -> 공유
```
to:
```python
"""[판정보류] - 전체 판정표는 docs/experiments_index.md 참고.

HNCS 실제 4단계 구조(조명별 3x3 매트릭스 -> 조명별 chroma LUT -> 공유
```

- [ ] **Step 9: `tools/evaluate_leica_de00_grid.py`**

Change:
```python
"""
Leica SL3-P / Q3 43 raw+jpeg 페어로 첫 raw 기반 캘리브레이션 - Sony a7V
```
to:
```python
"""[채택] - 전체 판정표는 docs/experiments_index.md 참고.

Leica SL3-P / Q3 43 raw+jpeg 페어로 첫 raw 기반 캘리브레이션 - Sony a7V
```

- [ ] **Step 10: `tools/evaluate_native_pixel_confirm.py`**

Change:
```python
"""
tools/evaluate_new_body_de00_grid.py / evaluate_hasselblad_body_de00_grid.py가
```
to:
```python
"""[채택] - 전체 판정표는 docs/experiments_index.md 참고.

tools/evaluate_new_body_de00_grid.py / evaluate_hasselblad_body_de00_grid.py가
```

- [ ] **Step 11: `tools/evaluate_new_body_de00_grid.py`**

Change:
```python
"""
신규 바디(2026-08 대량 추가분: Canon EOS R6 Mark III, Sony a7R VI,
```
to:
```python
"""[채택] - 전체 판정표는 docs/experiments_index.md 참고.

신규 바디(2026-08 대량 추가분: Canon EOS R6 Mark III, Sony a7R VI,
```

- [ ] **Step 12: `tools/evaluate_sony_a7v_de00.py`**

Change:
```python
"""
apply_sony_a7v_look()의 실제 ΔE00(CIEDE2000) - 지금까지 Sony a7V 검증은
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

apply_sony_a7v_look()의 실제 ΔE00(CIEDE2000) - 지금까지 Sony a7V 검증은
```

- [ ] **Step 13: `tools/evaluate_sony_a7v_de00_grid.py`**

Change:
```python
"""
Sony a7V 그리드서치를 ΔE00(CIEDE2000) 자체를 목적함수로 삼아 다시 돌린다 -
```
to:
```python
"""[채택] - 전체 판정표는 docs/experiments_index.md 참고.

Sony a7V 그리드서치를 ΔE00(CIEDE2000) 자체를 목적함수로 삼아 다시 돌린다 -
```

- [ ] **Step 14: `tools/evaluate_sony_a7v_grid_search.py`**

Change:
```python
"""
Sony a7 V(ILCE-7M5) 75쌍 raw+jpeg 페어로 진짜 전/후 그리드서치 - Sony는
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

Sony a7 V(ILCE-7M5) 75쌍 raw+jpeg 페어로 진짜 전/후 그리드서치 - Sony는
```

- [ ] **Step 15: `tools/evaluate_sony_body_split.py`**

Change:
```python
"""연구용 - Sony 5바디(A7/A7R/A7S/A7 III/A7 IV)의 population 통계에서,
hybrid_engine.convert의 소스 역산이 브랜드 전체 pooled 타깃 대신
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

연구용 - Sony 5바디(A7/A7R/A7S/A7 III/A7 IV)의 population 통계에서,
hybrid_engine.convert의 소스 역산이 브랜드 전체 pooled 타깃 대신
```

- [ ] **Step 16: `tools/evaluate_x2dii_color_matrix.py`**

Change:
```python
"""
X2D II 41쌍 자체에서 3x3 컬러 매트릭스를 직접 피팅(LOO)하면 apply_hncs()
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

X2D II 41쌍 자체에서 3x3 컬러 매트릭스를 직접 피팅(LOO)하면 apply_hncs()
```

- [ ] **Step 17: `tools/evaluate_x2dii_combined.py`**

Change:
```python
"""
X2D II ΔE00 감소 후보 세 개(학습LUT/분리감마/채도-hue보정, 각각
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

X2D II ΔE00 감소 후보 세 개(학습LUT/분리감마/채도-hue보정, 각각
```

- [ ] **Step 18: `tools/evaluate_x2dii_combo_a_full.py`**

Change:
```python
"""
콤보A(분리감마 shadow_gamma=0.4/highlight_gamma=0.3 고정 + 채도/hue LOO)의
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

콤보A(분리감마 shadow_gamma=0.4/highlight_gamma=0.3 고정 + 채도/hue LOO)의
```

- [ ] **Step 19: `tools/evaluate_x2dii_de00_check.py`**

Change:
```python
"""
apply_hncs_x2dii()의 실제 ΔE00/RMSE를 shoulder_start 정정(0.82->0.5)
```
to:
```python
"""[참고자료] - 전체 판정표는 docs/experiments_index.md 참고.

apply_hncs_x2dii()의 실제 ΔE00/RMSE를 shoulder_start 정정(0.82->0.5)
```

- [ ] **Step 20: `tools/evaluate_x2dii_de00_grid.py`**

Change:
```python
"""
X2D II 70쌍 그리드서치를 ΔE00(CIEDE2000) 자체를 목적함수로 다시 돌린다 -
```
to:
```python
"""[채택] - 전체 판정표는 docs/experiments_index.md 참고.

X2D II 70쌍 그리드서치를 ΔE00(CIEDE2000) 자체를 목적함수로 다시 돌린다 -
```

- [ ] **Step 21: `tools/evaluate_x2dii_generation_loo.py`**

Change:
```python
"""
X2D II 전용 파라미터가 풀링(main) 기본값 대비 유의미하게 나은지 -
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

X2D II 전용 파라미터가 풀링(main) 기본값 대비 유의미하게 나은지 -
```

- [ ] **Step 22: `tools/evaluate_x2dii_reduce_de00.py`**

Change:
```python
"""
apply_hncs_x2dii()의 실제 ΔE00 베이스라인을 재고, 더 낮출 수 있는 세
```
to:
```python
"""[기각] - 전체 판정표는 docs/experiments_index.md 참고.

apply_hncs_x2dii()의 실제 ΔE00 베이스라인을 재고, 더 낮출 수 있는 세
```

- [ ] **Step 23: Verify each of the 22 files starts with exactly one tag line**

```bash
python3 - <<'EOF'
import re

files = [
    "tools/evaluate_chromatic_aberration.py", "tools/evaluate_darktable_vs_rawpy.py",
    "tools/evaluate_exposure_gamma_x2dii.py", "tools/evaluate_fuji_demosaic.py",
    "tools/evaluate_full_pixel_de00_confirm.py", "tools/evaluate_hasselblad_body_de00_grid.py",
    "tools/evaluate_hncs_blend.py", "tools/evaluate_hncs_structural.py",
    "tools/evaluate_leica_de00_grid.py", "tools/evaluate_native_pixel_confirm.py",
    "tools/evaluate_new_body_de00_grid.py", "tools/evaluate_sony_a7v_de00.py",
    "tools/evaluate_sony_a7v_de00_grid.py", "tools/evaluate_sony_a7v_grid_search.py",
    "tools/evaluate_sony_body_split.py", "tools/evaluate_x2dii_color_matrix.py",
    "tools/evaluate_x2dii_combined.py", "tools/evaluate_x2dii_combo_a_full.py",
    "tools/evaluate_x2dii_de00_check.py", "tools/evaluate_x2dii_de00_grid.py",
    "tools/evaluate_x2dii_generation_loo.py", "tools/evaluate_x2dii_reduce_de00.py",
]
pattern = re.compile(r'^"""\[(채택|기각|판정보류|참고자료)\] - 전체 판정표는 docs/experiments_index\.md 참고\.$')
for path in files:
    first_line = open(path).readline().rstrip("\n")
    assert pattern.match(first_line), f"{path}: first line is {first_line!r}"
print(f"all {len(files)} files tagged correctly")
EOF
```

Expected: `all 22 files tagged correctly`

- [ ] **Step 24: Confirm no file outside this list changed, and no
  `brands/*.py`/test file was touched**

```bash
git status --short
```

Expected: only the 22 files listed above appear as modified.

- [ ] **Step 25: Run the full test suite**

```bash
python3 -m unittest discover -s tests
```

Expected: same pass/fail counts as before this task (docstring-only
change).

- [ ] **Step 26: Commit**

```bash
git add tools/evaluate_chromatic_aberration.py tools/evaluate_darktable_vs_rawpy.py \
        tools/evaluate_exposure_gamma_x2dii.py tools/evaluate_fuji_demosaic.py \
        tools/evaluate_full_pixel_de00_confirm.py tools/evaluate_hasselblad_body_de00_grid.py \
        tools/evaluate_hncs_blend.py tools/evaluate_hncs_structural.py \
        tools/evaluate_leica_de00_grid.py tools/evaluate_native_pixel_confirm.py \
        tools/evaluate_new_body_de00_grid.py tools/evaluate_sony_a7v_de00.py \
        tools/evaluate_sony_a7v_de00_grid.py tools/evaluate_sony_a7v_grid_search.py \
        tools/evaluate_sony_body_split.py tools/evaluate_x2dii_color_matrix.py \
        tools/evaluate_x2dii_combined.py tools/evaluate_x2dii_combo_a_full.py \
        tools/evaluate_x2dii_de00_check.py tools/evaluate_x2dii_de00_grid.py \
        tools/evaluate_x2dii_generation_loo.py tools/evaluate_x2dii_reduce_de00.py
git commit -m "Tag all 22 tools/evaluate_*.py docstrings with their verdict"
```

---

### Task 3: Tag the 22 rows in `docs/project_structure.md` and `.en.md`

**Files:**
- Modify: `docs/project_structure.md`
- Modify: `docs/project_structure.en.md`

**Interfaces:**
- Consumes: nothing from Tasks 1-2 except the master tag table (Global
  Constraints section above).
- Produces: nothing consumed by later tasks — this is the last task in
  this plan.

Both files list each `tools/evaluate_*.py` as a markdown table row in
the exact format `| \`tools/<name>.py\` | <description...> |`. For each
of the 22 files, prepend the tag (in Korean, `[채택]`/`[기각]`/
`[판정보류]`/`[참고자료]` — same in both language versions, since it's a
fixed short enum rather than prose) immediately after the closing
backtick-and-pipe of the filename cell, before the existing description
text, in both `docs/project_structure.md` and `docs/project_structure.en.md`.

Concretely, in `docs/project_structure.md`, a row currently reading:
```
| `tools/evaluate_chromatic_aberration.py` | 연구용 - rawpy `chromatic_aberration`(R/B 채널 스케일링) ...
```
becomes:
```
| `tools/evaluate_chromatic_aberration.py` | [기각] 연구용 - rawpy `chromatic_aberration`(R/B 채널 스케일링) ...
```
i.e. insert `[기각] ` (tag, space) as a prefix to the existing
description cell's text — the rest of that cell's text is untouched.
Apply this same prefix-insertion pattern to the row for each of the 22
files below, in both `docs/project_structure.md` and
`docs/project_structure.en.md`, using each file's tag from the Global
Constraints master table above:

- `evaluate_chromatic_aberration.py` → `[기각]`
- `evaluate_darktable_vs_rawpy.py` → `[기각]`
- `evaluate_exposure_gamma_x2dii.py` → `[기각]`
- `evaluate_fuji_demosaic.py` → `[참고자료]`
- `evaluate_full_pixel_de00_confirm.py` → `[참고자료]`
- `evaluate_hasselblad_body_de00_grid.py` → `[채택]`
- `evaluate_hncs_blend.py` → `[판정보류]`
- `evaluate_hncs_structural.py` → `[판정보류]`
- `evaluate_leica_de00_grid.py` → `[채택]`
- `evaluate_native_pixel_confirm.py` → `[채택]`
- `evaluate_new_body_de00_grid.py` → `[채택]`
- `evaluate_sony_a7v_de00.py` → `[기각]`
- `evaluate_sony_a7v_de00_grid.py` → `[채택]`
- `evaluate_sony_a7v_grid_search.py` → `[기각]`
- `evaluate_sony_body_split.py` → `[기각]`
- `evaluate_x2dii_color_matrix.py` → `[기각]`
- `evaluate_x2dii_combined.py` → `[기각]`
- `evaluate_x2dii_combo_a_full.py` → `[기각]`
- `evaluate_x2dii_de00_check.py` → `[참고자료]`
- `evaluate_x2dii_de00_grid.py` → `[채택]`
- `evaluate_x2dii_generation_loo.py` → `[기각]`
- `evaluate_x2dii_reduce_de00.py` → `[기각]`

Do not alter anything else in either row (the file-path cell, the rest
of the description text, or any other row in the table).

- [ ] **Step 1: Find each of the 22 rows in `docs/project_structure.md`**

```bash
grep -n "tools/evaluate_chromatic_aberration\.py\`\|tools/evaluate_darktable_vs_rawpy\.py\`\|tools/evaluate_exposure_gamma_x2dii\.py\`\|tools/evaluate_fuji_demosaic\.py\`\|tools/evaluate_full_pixel_de00_confirm\.py\`\|tools/evaluate_hasselblad_body_de00_grid\.py\`\|tools/evaluate_hncs_blend\.py\`\|tools/evaluate_hncs_structural\.py\`\|tools/evaluate_leica_de00_grid\.py\`\|tools/evaluate_native_pixel_confirm\.py\`\|tools/evaluate_new_body_de00_grid\.py\`\|tools/evaluate_sony_a7v_de00\.py\`\|tools/evaluate_sony_a7v_de00_grid\.py\`\|tools/evaluate_sony_a7v_grid_search\.py\`\|tools/evaluate_sony_body_split\.py\`\|tools/evaluate_x2dii_color_matrix\.py\`\|tools/evaluate_x2dii_combined\.py\`\|tools/evaluate_x2dii_combo_a_full\.py\`\|tools/evaluate_x2dii_de00_check\.py\`\|tools/evaluate_x2dii_de00_grid\.py\`\|tools/evaluate_x2dii_generation_loo\.py\`\|tools/evaluate_x2dii_reduce_de00\.py\`" docs/project_structure.md
```

For each matched line, use the Edit tool: `old_string` is
`` | `tools/<name>.py` | `` (the exact filename cell plus the following
pipe-and-space), `new_string` is the same text plus the tag and a space
appended (e.g. `` | `tools/evaluate_chromatic_aberration.py` | [기각] ``).
This is a unique anchor per row since each filename appears exactly once
in the table.

- [ ] **Step 2: Repeat Step 1's grep + Edit pattern for
  `docs/project_structure.en.md`**

Same 22 rows, same tags (tags are the fixed Korean-bracket enum in both
language files per the Global Constraints note above).

- [ ] **Step 3: Verify all 22 rows are tagged in both files**

```bash
python3 - <<'EOF'
import re

tags = {
    "evaluate_chromatic_aberration": "기각", "evaluate_darktable_vs_rawpy": "기각",
    "evaluate_exposure_gamma_x2dii": "기각", "evaluate_fuji_demosaic": "참고자료",
    "evaluate_full_pixel_de00_confirm": "참고자료", "evaluate_hasselblad_body_de00_grid": "채택",
    "evaluate_hncs_blend": "판정보류", "evaluate_hncs_structural": "판정보류",
    "evaluate_leica_de00_grid": "채택", "evaluate_native_pixel_confirm": "채택",
    "evaluate_new_body_de00_grid": "채택", "evaluate_sony_a7v_de00": "기각",
    "evaluate_sony_a7v_de00_grid": "채택", "evaluate_sony_a7v_grid_search": "기각",
    "evaluate_sony_body_split": "기각", "evaluate_x2dii_color_matrix": "기각",
    "evaluate_x2dii_combined": "기각", "evaluate_x2dii_combo_a_full": "기각",
    "evaluate_x2dii_de00_check": "참고자료", "evaluate_x2dii_de00_grid": "채택",
    "evaluate_x2dii_generation_loo": "기각", "evaluate_x2dii_reduce_de00": "기각",
}
for doc in ["docs/project_structure.md", "docs/project_structure.en.md"]:
    text = open(doc).read()
    for name, tag in tags.items():
        pattern = re.compile(rf"\|\s*`tools/{name}\.py`\s*\|\s*\[{tag}\]")
        assert pattern.search(text), f"{doc}: {name}.py missing [{tag}] tag"
print("all 22 rows tagged correctly in both files")
EOF
```

Expected: `all 22 rows tagged correctly in both files`

- [ ] **Step 4: Confirm `brands/hasselblad.py` and no other unintended
  file changed**

```bash
git status --short
```

Expected: only `docs/project_structure.md` and
`docs/project_structure.en.md` appear as modified.

- [ ] **Step 5: Run the full test suite**

```bash
python3 -m unittest discover -s tests
```

Expected: same pass/fail counts as before this task (docs-only change).

- [ ] **Step 6: Commit**

```bash
git add docs/project_structure.md docs/project_structure.en.md
git commit -m "Tag 22 tools/evaluate_*.py rows in project_structure.md(.en.md) with their verdict"
```
