"""Local replay of the fixed Provia/identity-foundation, 512px evaluator.

Never execute a receipt's command or accept an evaluator supplied by evidence.
Exact comparisons deliberately fail closed across numerical runtime drift.
This authenticates computation on the local code, not capture truth or a signer.
"""
import json


def replay_metrics(manifest, submitted):
    from brands.fuji import apply_provia
    from .nare_runner import run_nare_metrics

    try:
        actual = run_nare_metrics(manifest, 'F0/Standard (Provia)',
                                  candidate=apply_provia, max_dim=512)
    except Exception as error:
        raise ValueError(f'NARE replay failed: {error}') from error

    def canonical(rows):
        return json.dumps(sorted(rows, key=lambda row: row['scene_id']),
                          sort_keys=True, allow_nan=False, separators=(',', ':'))

    if canonical(submitted) != canonical(actual):
        raise ValueError('NARE replay metrics do not match submitted metrics')
    return actual
