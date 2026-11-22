"""Serializable resistance functions on normalized lifting travel, in kgf per kg of plates."""

from bisect import bisect_right
from math import isfinite

import numpy as np
from numpy.polynomial import Polynomial
from scipy.interpolate import PchipInterpolator


def _coefficients(values):
    # Keep machine-record diffs readable across numerical library versions.
    return [float(f"{v:.12g}") for v in values]


def evaluate_curve(curve, travel):
    """Return kgf/kg at a stroke fraction in [0, 1]."""
    if not isfinite(travel) or not 0 <= travel <= 1:
        raise ValueError("Travel must be a finite fraction from 0 to 1.")
    coefficients = curve["coefficients"]
    if curve["type"] in ("pchip", "interval_mean"):
        knots = curve["knots"]
        i = min(bisect_right(knots, travel) - 1, len(knots) - 2)
        coefficients = coefficients[i]
        travel -= knots[i]
    value = 0.0
    for coefficient in reversed(coefficients):
        value = value * travel + coefficient
    return max(0.0, value)  # Roundoff at a zero-force endpoint.


def fit_curve(points):
    """Prefer the lowest adequate degree through cubic, then shape-preserving interpolation."""
    data = np.asarray(points, dtype=float)
    if data.ndim != 2 or data.shape[1] != 2 or len(data) < 2 or not np.isfinite(data).all():
        raise ValueError("Expected at least two finite [travel fraction, force ratio] pairs.")
    x, y = data.T
    if x[0] != 0 or x[-1] != 1 or np.any(np.diff(x) <= 0) or np.any(y < 0):
        raise ValueError("Travel must increase from 0 to 1 and force ratios must be nonnegative.")
    tolerance = float(np.max(y)) * 0.01
    line = Polynomial([y[0], y[-1] - y[0]])
    basis = Polynomial([0, 1, -1])  # x(1-x) preserves both endpoint values.
    for degree in range(min(3, len(x) - 1) + 1):
        if degree == 0:
            if not np.all(y == y[0]):
                continue
            poly = Polynomial([y[0]])
        elif degree == 1:
            poly = line
        else:
            design = basis(x)[:, None] * np.vander(x, degree - 1, increasing=True)
            correction, *_ = np.linalg.lstsq(design, y - line(x), rcond=None)
            poly = line + basis * Polynomial(correction)
        error = np.max(np.abs(poly(x) - y))
        if error > tolerance:
            continue
        # Check every interior extremum, including in widely spaced photo intervals.
        for root in poly.deriv().roots():
            if not np.isreal(root) or not 0 < root.real < 1:
                continue
            i = x.searchsorted(root.real)
            low, high = sorted(y[i-1:i+1])
            value = poly(root.real)
            if value < max(0, low - tolerance) or value > high + tolerance:
                break
        else:
            curve = {"type": "polynomial", "coefficients": _coefficients(poly.coef)}
            break
    else:
        spline = PchipInterpolator(x, y)
        curve = {"type": "pchip", "knots": x.tolist(),
                 "coefficients": [_coefficients(row[::-1]) for row in spline.c.T]}
    curve.update(input="stroke_fraction", domain=[0, 1], output="kgf_per_kg",
                 sample_count=len(x))
    error = max(abs(evaluate_curve(curve, t) - f) for t, f in points)
    curve["max_sample_error_kgf_per_kg"] = float(f"{error:.4g}") if error > 1e-12 * max(y) else 0.0
    return curve
