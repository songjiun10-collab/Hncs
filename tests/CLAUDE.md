# tests/

```bash
python3 -m unittest discover -s tests
```

Full suite green before every commit. `unittest` only, no pytest.

## CI has no image data

`raw_calib_cache/`, `downloaded_samples*/` and the contributed datasets
are all git-ignored. **Never commit a test that needs them** — it passes
locally and fails in CI.

Instead:
- unit-test the pure parts (CSV parsing, path resolution, statistics,
  math helpers)
- mock the decode layer (`@patch("...io.rawpy.imread")` etc.)
- run the real measurement manually, record the output in the task report
  and `hybrid_engine/EVALUATION.md`

## `TestSummarizeRecordedRun`

The pattern that makes long experiments auditable: hardcode the real
per-fold results from the run log, feed them through the actual
`summarize()`, assert it reproduces the numbers published in
`EVALUATION.md`. Now anyone can verify the documented statistics without
re-running a multi-hour experiment.

Copy it for every new comparison experiment. Assert at the precision the
published table actually supports — a 3-decimal table doesn't reproduce a
6-decimal mean.

## Tests must be able to fail

Write the test first, run it, confirm it fails for the right reason. A
boundary test that asserts against a hand-computed constant is worth more
than one that asserts against whatever the code currently returns.

## A failing golden-hash test might already be fixed upstream

A session hit 7 failing entries in the golden byte-hash tests
(`test_population_fit_look_golden.py`), spent real time reinstalling
opencv and A/B-testing versions, and committed a confident but wrong
root cause ("a recording mistake, not a code regression"). A different
session had already fixed the same 7 hashes a day earlier on `main`,
with the actual cause: `requirements.txt` had no version pins, so CI and
local environments resolved different opencv builds and the HSV-roundtrip
functions' lowest bits genuinely differed. The recovered hash *values*
matched byte-for-byte (real independent verification), but the root-cause
story didn't — a fixed value with a wrong explanation still ends up
committed and read by the next session. Before treating a golden-hash
mismatch as "these values are just stale," check `git log origin/main --
<this file>` first — see root `CLAUDE.md`'s "Think before coding".
