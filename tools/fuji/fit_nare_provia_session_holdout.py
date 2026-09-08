"""Session-holdout Provia fitting on a registration-passed NARE manifest.

Research only: this script never edits a shipped ``apply_*`` implementation.
It fits shoulder_start/clahe_clip on complete capture sessions and scores the
held-out session, keeping the NARE scene unit from leaking across bursts.
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from brands.fuji import apply_provia
from hybrid_engine.evaluation.nare_registration import register_to_target
from hybrid_engine.utils.evaluate import bgr_u8_to_linear_rgb, mean_delta_e
from tools.fit.calibrate import load_neutral_render


GRID = [(shoulder, clip) for shoulder in (0.66, 0.70, 0.74, 0.78, 0.82)
        for clip in (1.25, 2.0, 3.0)]


def _load_frame(row: dict, max_dim: int) -> dict:
    neutral = load_neutral_render(row["source_path"], max_dim=max_dim)
    target = cv2.imread(row["target_path"], cv2.IMREAD_COLOR)
    if target is None:
        raise ValueError(f"unreadable target: {row['target_path']}")
    target = cv2.resize(target, (neutral.shape[1], neutral.shape[0]), interpolation=cv2.INTER_AREA)
    aligned, valid, registration = register_to_target(neutral, target)
    return {"scene_id": row["scene_id"], "session_id": row["session_id"],
            "neutral": aligned, "target": bgr_u8_to_linear_rgb(target)[valid],
            "valid": valid, "registration": registration}


def _score(frame: dict, shoulder: float, clip: float) -> float:
    rendered = apply_provia(frame["neutral"], shoulder_start=shoulder, clahe_clip=clip)
    return mean_delta_e(bgr_u8_to_linear_rgb(rendered)[frame["valid"]], frame["target"])


def fit(manifest: list[dict], max_dim: int = 512) -> dict:
    frames = [_load_frame(row, max_dim) for row in manifest]
    by_session: dict[str, list[dict]] = defaultdict(list)
    for frame in frames:
        by_session[frame["session_id"]].append(frame)
    if len(by_session) < 3:
        raise ValueError("need at least three independent sessions for holdout fit")
    score_matrix = np.asarray([[_score(frame, *combo) for combo in GRID] for frame in frames])
    current_scores = np.asarray([_score(frame, 0.82, 3.0) for frame in frames])
    session_names = [frame["session_id"] for frame in frames]
    rows = []
    per_scene = []
    for held_out in sorted(by_session):
        train_idx = np.asarray([i for i, session in enumerate(session_names) if session != held_out])
        test_idx = np.asarray([i for i, session in enumerate(session_names) if session == held_out])
        best_index = int(np.argmin(score_matrix[train_idx].mean(axis=0)))
        best = GRID[best_index]
        candidate = score_matrix[test_idx, best_index]
        current = current_scores[test_idx]
        for index, candidate_score, current_score in zip(test_idx, candidate, current):
            per_scene.append({"scene_id": frames[index]["scene_id"],
                              "held_out_session": held_out,
                              "current_delta_e00": float(current_score),
                              "candidate_delta_e00": float(candidate_score),
                              "improvement": float(current_score - candidate_score)})
        rows.append({"held_out_session": held_out, "n_train": len(train_idx),
                     "n_test": len(test_idx), "shoulder_start": best[0], "clahe_clip": best[1],
                     "current_mean_delta_e00": float(np.mean(current)),
                     "candidate_mean_delta_e00": float(np.mean(candidate)),
                     "improvement_pct": float(100 * (np.mean(current) - np.mean(candidate)) / np.mean(current))})
    improvements = np.asarray([row["improvement"] for row in per_scene])
    rng = np.random.RandomState(0)
    bootstrap = np.asarray([rng.choice(improvements, len(improvements), replace=True).mean()
                            for _ in range(20_000)])
    wins = int((improvements > 0).sum())
    losses = int((improvements < 0).sum())
    tail = sum(math.comb(wins + losses, i) for i in range(min(wins, losses) + 1)) / 2 ** (wins + losses)
    return {"max_dim": max_dim, "grid": GRID, "n_scenes": len(frames),
            "n_sessions": len(by_session), "folds": rows,
            "per_scene": per_scene,
            "mean_current_delta_e00": float(current_scores.mean()),
            "mean_candidate_delta_e00": float(current_scores.mean() - improvements.mean()),
            "improvement": float(improvements.mean()),
            "improvement_pct": float(100 * improvements.mean() / current_scores.mean()),
            "ci95": [float(np.percentile(bootstrap, 2.5)), float(np.percentile(bootstrap, 97.5))],
            "wins": wins, "losses": losses,
            "sign_test_p": float(min(1.0, 2 * tail))}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fit Provia parameters with session holdout")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--max-dim", type=int, default=512)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    report = fit(json.loads(Path(args.manifest).read_text(encoding="utf-8")), args.max_dim)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"session-holdout fit: {report['n_sessions']} sessions, {report['n_scenes']} scenes")


if __name__ == "__main__":
    main()
