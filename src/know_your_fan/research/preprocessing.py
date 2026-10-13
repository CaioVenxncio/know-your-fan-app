"""Preprocessing strategies compared in the experiments.

``P0_baseline`` is exactly the application's own ``ocr.preprocess`` (EXIF
transpose, grayscale, autocontrast). The others isolate one change each
(ablations) plus one combination:

* ``P1_none``: no preprocessing; Tesseract binarizes internally.
* ``P2_gray``: grayscale only (P0 without autocontrast).
* ``P3_otsu``: P0 + Otsu global threshold.
* ``P4_median``: P0 + 3x3 median filter.
* ``P5_upscale2``: P0 + 2x Lanczos upscaling.
* ``P6_invert``: P0 + inversion (what the original 2025 app did).
* ``P7_upscale2_otsu``: P0 + 2x upscaling + Otsu threshold.
"""

from __future__ import annotations

from collections.abc import Callable

from PIL import Image, ImageFilter, ImageOps

from know_your_fan import ocr

Preprocessor = Callable[[Image.Image], Image.Image]


def otsu_threshold(gray: Image.Image) -> int:
    """Otsu's threshold for an 8-bit grayscale image (maximizes between-class variance)."""
    if gray.mode != "L":
        raise ValueError("otsu_threshold expects a mode 'L' image")
    histogram = gray.histogram()
    total = sum(histogram)
    total_sum = sum(i * count for i, count in enumerate(histogram))
    background = background_sum = 0
    best_threshold, best_variance = 0, -1.0
    for threshold, count in enumerate(histogram):
        background += count
        if background == 0:
            continue
        foreground = total - background
        if foreground == 0:
            break
        background_sum += threshold * count
        mean_b = background_sum / background
        mean_f = (total_sum - background_sum) / foreground
        variance = background * foreground * (mean_b - mean_f) ** 2
        if variance > best_variance:
            best_threshold, best_variance = threshold, variance
    return best_threshold


def binarize(gray: Image.Image) -> Image.Image:
    threshold = otsu_threshold(gray)
    return gray.point(lambda value: 255 if value > threshold else 0)


def upscale2(image: Image.Image) -> Image.Image:
    return image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)


STRATEGIES: dict[str, Preprocessor] = {
    "P0_baseline": ocr.preprocess,
    "P1_none": lambda image: image.convert("RGB"),
    "P2_gray": ImageOps.grayscale,
    "P3_otsu": lambda image: binarize(ocr.preprocess(image)),
    "P4_median": lambda image: ocr.preprocess(image).filter(ImageFilter.MedianFilter(3)),
    "P5_upscale2": lambda image: upscale2(ocr.preprocess(image)),
    "P6_invert": lambda image: ImageOps.invert(ocr.preprocess(image)),
    "P7_upscale2_otsu": lambda image: binarize(upscale2(ocr.preprocess(image))),
}
