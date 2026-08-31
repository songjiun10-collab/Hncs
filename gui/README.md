# gui/ - Desktop App

A Tkinter desktop app that wraps the CLIs from `tools/` and
`hybrid_engine/` into one window with 4 tabs - brand look preview,
hybrid_engine conversion, RAW->Log pipeline, and lens correction. Pure
wrapper: no new color-science logic, just point-and-click over the same
commands documented in `tools/README.md` and `hybrid_engine/README.md`.

```
pip install -r requirements.txt   # now includes Pillow, needed to display images in Tk
python3 -m gui
```

Run from the repo root so the `core`/`brands`/`tools`/`hybrid_engine`
import paths resolve correctly.

Tkinter itself is in the Python standard library, but some distributions
(e.g. Homebrew Python on macOS) split it into a separate system package
(`python-tk`) - install that if `python3 -m gui` fails with a Tkinter
import error.

The lens-correction tab's usefulness depends entirely on the bundled
lensfun camera/lens database's coverage - e.g. it only has 4 old
Hasselblad camera entries with zero lens data, so it fails with
`lens_not_found` on every Hasselblad RAW sample.
