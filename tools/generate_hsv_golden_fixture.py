"""Regenerate the platform-tolerant HSV golden-output fixture.

Run only after approving a new known-good baseline:

    .venv/bin/python tools/generate_hsv_golden_fixture.py
"""
import importlib
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_population_fit_look_golden import (
    HSV_ROUND_TRIP_FUNCTIONS,
    make_test_image,
)


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "hsv_golden_outputs.npz"


def main():
    outputs = {}
    for mod_name, fn_name in HSV_ROUND_TRIP_FUNCTIONS:
        outputs[fn_name] = getattr(importlib.import_module(mod_name), fn_name)(
            make_test_image()
        )

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FIXTURE_PATH, **outputs)
    print(f"wrote {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
