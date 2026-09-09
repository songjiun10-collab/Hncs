# NARE replay and per-image registration validation

[한국어](2026-09-09-nare-replay-registration.md)

Correction to prior completion claims: existing files, matching hashes and a
self-signed receipt did not establish execution. Receipt-backed NARE reports now
run the local fixed Provia, identity-foundation, 512px evaluator and compare the
complete submitted metrics against its output. Receipt commands are never run.
Replay failures or differences reject the evidence; reports use recomputed rows.
Additional evaluators and scales require explicit implementation support.

The current runner produces no semantic ROI measurements. Submitted JSON cannot
supplement them. Successful replays therefore remain Inconclusive at the subgroup
gate. Supported is not redefined as mere artifact integrity. Capture truth and
independent runner authentication remain outside this local replay guarantee.
Exact comparisons fail closed on runtime numerical drift; regenerate evidence in
the same environment when necessary.

Scene errors remain image-weighted means. Registration retains a frames array and
validates every image using its own resolution and shift vector. It no longer
combines unrelated x/y maxima or hides failures behind the first image. Single
image diagnostics retain their existing shape.

Tests in tests.test_nare_execution_boundary cover orthogonal shifts, scales,
failure and missing diagnostics, invented metrics and semantic fields, matching
replays, scene ordering, and a real-runner positive control. That control mocks
only decoding, exercising registration, colour computation, signature checks and
report generation.
