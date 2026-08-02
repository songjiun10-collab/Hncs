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
