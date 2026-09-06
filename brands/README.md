# brands/

*[한국어 README](README.ko.md)*

Per-brand color-approximation functions (`apply_*`) - the shipped
artifact. See this directory's `CLAUDE.md` for the rules that govern
changes here.

## Supported Brands

| Brand | Verification method | Details |
|---|---|---|
| ✅ Hasselblad | raw+jpeg pair calibration (grid search + learned LUT) | [docs/measurements.en.md](../docs/measurements.en.md) |
| ✅ Fujifilm | 11 film-simulation presets, population + same-scene comparison charts + raw+jpeg (Provia) | [docs/brands.en.md](../docs/brands.en.md#fujifilm-brandsfujilookpy) |
| ✅ Leica | population-fit (45 SOOC JPEGs) | [docs/brands.en.md](../docs/brands.en.md#leica-brandsleicalookpy) |
| ✅ Phase One | population-fit (Capture One's default rendering) | [docs/brands.en.md](../docs/brands.en.md#phase-one-brandsphaseonelookpy) |
| ✅ Pentax | population-fit (645Z + K-1, 40 photos) | [docs/brands.en.md](../docs/brands.en.md#pentax-brandspentaxlookpy) |
| ✅ Ricoh GR | population-fit (GR III/IIIx/II) | [docs/brands.en.md](../docs/brands.en.md#ricoh-gr-brandsricoh_grlookpy) |
| ✅ Canon | population-fit (EOS R5/R6/R8/R3/R, n=115) | `canon/look.py` docstring |
| ✅ Nikon | population-fit (Z6/Z6 II/D780, n=69) | `nikon/look.py` docstring |
| ✅ Sony | population-fit (A7/A7R/A7S/A7 III/A7 IV, n=115) | `sony/look.py` docstring |
| ✅ Panasonic | population-fit (GH5/GH6/G9/S5/S1, n=120) | `panasonic/look.py` docstring |
| ✅ Olympus | population-fit (OM-1/OM-5/E-M1 III/E-M1X/PEN-F, n=122) | `olympus/look.py` docstring |
| ✅ Sigma | population-fit (Bayer + Foveon, 5 bodies, n=83) | `sigma/look.py` docstring |

The shared limitations of the population-fit approach (no raw baseline;
some parameters like shoulder_start/clahe_clip are borrowed from
Hasselblad's values and unverified) are documented in detail in
[docs/brands.en.md](../docs/brands.en.md) and each `*.py` docstring in
this directory.

## Quick Example

```python
import cv2
from brands.hasselblad import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

Every `apply_*` function here uniformly takes a BGR `np.ndarray` and
returns a same-shape `np.ndarray`. The two monochrome film simulations
(`apply_acros`, `apply_monochrome`) return a single-channel 2D array
rather than 3-channel BGR - deliberate, and covered by
`tests/test_brands.py`. Run from the repo root so the `core`/`brands`/
`tools` import paths resolve correctly.

## Layout

One package per brand, flat modules inside it - `brands/<brand>/look.py`
is the brand's primary look and `brands/<brand>/<variant>.py` its
body-specific or experimental variants (`hasselblad/x2dii.py`,
`sony/a7v_learned.py`). Each package's `__init__.py` re-exports every
public `apply_*`, so `from brands.hasselblad import apply_hncs` works
unchanged. The files were flat until 2026-09-06; the regrouping moved
them without editing a single `apply_*` body.
