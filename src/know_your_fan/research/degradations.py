"""Controlled, seeded image degradations for the OCR experiments.

Order of operations (fixed): rotation -> Gaussian blur -> downscaling -> additive
Gaussian noise. Noise is added last, at the final resolution, like sensor
noise. Every parameter is validated, and the noise generator is seeded per
(sample, condition), so the same inputs always give the same pixels.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

MAX_BLUR_SIGMA = 4.0
MAX_ROTATION_DEGREES = 15.0
MAX_NOISE_SIGMA = 64.0
MIN_SCALE = 0.25


@dataclass(frozen=True, slots=True)
class Degradation:
    """Explicit degradation parameters. ``scale`` is the linear resolution factor."""

    name: str
    blur_sigma: float = 0.0
    rotation_degrees: float = 0.0
    noise_sigma: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        values = (self.blur_sigma, self.rotation_degrees, self.noise_sigma, self.scale)
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"{self.name}: degradation parameters must be finite")
        if not 0 <= self.blur_sigma <= MAX_BLUR_SIGMA:
            raise ValueError(f"{self.name}: blur_sigma must be in [0, {MAX_BLUR_SIGMA}]")
        if abs(self.rotation_degrees) > MAX_ROTATION_DEGREES:
            raise ValueError(f"{self.name}: |rotation_degrees| must be <= {MAX_ROTATION_DEGREES}")
        if not 0 <= self.noise_sigma <= MAX_NOISE_SIGMA:
            raise ValueError(f"{self.name}: noise_sigma must be in [0, {MAX_NOISE_SIGMA}]")
        if not MIN_SCALE <= self.scale <= 1.0:
            raise ValueError(f"{self.name}: scale must be in [{MIN_SCALE}, 1]")

    @property
    def family(self) -> str:
        active = [
            label
            for label, value in (
                ("blur", self.blur_sigma),
                ("rotation", self.rotation_degrees),
                ("noise", self.noise_sigma),
                ("resolution", 1.0 - self.scale),
            )
            if value
        ]
        if not active:
            return "clean"
        return active[0] if len(active) == 1 else "combined"


# One-factor-at-a-time levels plus two combinations (see methodology.md).
CONDITIONS: dict[str, Degradation] = {
    d.name: d
    for d in (
        Degradation("clean"),
        Degradation("blur_1", blur_sigma=1.0),
        Degradation("blur_2", blur_sigma=2.0),
        Degradation("blur_3", blur_sigma=3.0),
        Degradation("rot_-3", rotation_degrees=-3.0),
        Degradation("rot_+3", rotation_degrees=3.0),
        Degradation("rot_-8", rotation_degrees=-8.0),
        Degradation("rot_+8", rotation_degrees=8.0),
        Degradation("noise_10", noise_sigma=10.0),
        Degradation("noise_25", noise_sigma=25.0),
        Degradation("noise_40", noise_sigma=40.0),
        Degradation("res_0.60", scale=0.60),
        Degradation("res_0.45", scale=0.45),
        Degradation("res_0.30", scale=0.30),
        Degradation(
            "combo_mild", blur_sigma=1.0, rotation_degrees=3.0, noise_sigma=10.0, scale=0.60
        ),
        Degradation(
            "combo_moderate", blur_sigma=2.0, rotation_degrees=-8.0, noise_sigma=25.0, scale=0.45
        ),
    )
}


def noise_seed(dataset_seed: int, source_id: str, condition: str) -> int:
    key = f"{dataset_seed}|{source_id}|{condition}|noise".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def apply(image: Image.Image, degradation: Degradation, seed: int) -> Image.Image:
    """Return a degraded RGB copy of ``image``; the input is never modified."""
    result = image.convert("RGB")
    if degradation.rotation_degrees:
        result = result.rotate(
            degradation.rotation_degrees,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor="white",
        )
    if degradation.blur_sigma:
        result = result.filter(ImageFilter.GaussianBlur(degradation.blur_sigma))
    if degradation.scale != 1.0:
        width, height = result.size
        size = (max(1, round(width * degradation.scale)), max(1, round(height * degradation.scale)))
        result = result.resize(size, Image.Resampling.LANCZOS)
    if degradation.noise_sigma:
        rng = np.random.default_rng(seed)
        pixels = np.asarray(result, dtype=np.float32)
        noisy = pixels + rng.normal(0.0, degradation.noise_sigma, size=pixels.shape)
        result = Image.fromarray(np.clip(np.rint(noisy), 0, 255).astype(np.uint8), mode="RGB")
    return result
