"""Shared data and colour helpers for evaluation tools."""

import csv
import os
import subprocess

import colour
import cv2
import numpy as np


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _exif_film_mode(jpg_path):
    out = subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                         capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


def collect_contributed_pairs(brand, model_filter=None, film_mode_filter=None):
    """Collect contributed raw/JPEG pairs in deterministic set order."""
    base = os.path.join(BASE, "datasets", brand, "contributed")
    pairs = []
    seen = set()
    if not os.path.isdir(base):
        return pairs
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        with open(manifest, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["filename_raw"] in seen:
                    continue
                if model_filter and row.get("camera") != model_filter:
                    continue
                raw_path = os.path.join(base, set_name, "raw", row["filename_raw"])
                jpg_path = os.path.join(base, set_name, "jpeg", row["filename_jpeg"])
                if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
                    continue
                if film_mode_filter and _exif_film_mode(jpg_path) != film_mode_filter:
                    continue
                seen.add(row["filename_raw"])
                pairs.append(dict(name=row["filename_raw"], raw_path=raw_path, jpeg_path=jpg_path))
    return pairs


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))
