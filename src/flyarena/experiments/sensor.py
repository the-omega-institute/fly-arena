"""Stateless local chemical approximation. No wind, diffusion or wall occlusion."""
import numpy as np

SENSOR = {"id": "bilateral-current-v2", "half_saturation": .3, "contrast_gain": 6.,
          "contrast_fraction": .8, "current_mv": 48., "background_mv": 0.,
          "inputs": ["left local chemical concentration", "right local chemical concentration"],
          "approximation": "analytic concentration fixture; no diffusion, vision or contact feedback"}

def encode_odor(left: float, right: float) -> np.ndarray:
    raw = np.asarray([left, right], dtype=float)
    if not np.isfinite(raw).all() or np.any(raw < 0):
        raise ValueError("odor must be finite and nonnegative")
    common = float(raw.mean() / (raw.mean() + SENSOR["half_saturation"]))
    contrast = float((left - right) / (left + right + .05))
    gain = SENSOR["contrast_fraction"] * np.tanh(SENSOR["contrast_gain"] * contrast)
    encoded = common * np.array([1 + gain, 1 - gain])
    # One shared gain preserves contrast, even when summed sources exceed one.
    return encoded / max(1., float(encoded.max()))
