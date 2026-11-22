"""Estimate plate-induced tangential resistance from motion in registered frames."""

from itertools import accumulate, pairwise
from math import dist, isfinite


def registered_paths(poses, keys):
    if not isinstance(poses, list) or len(poses) < 2:
        raise ValueError("A motion estimate needs two or more ordered frames.")
    paths = {key: [] for key in keys}
    for pose in poses:
        for key in ("anchor", *keys):
            point = pose.get(key)
            if not (isinstance(point, list) and len(point) == 2 and
                    all(type(n) in (int, float) and isfinite(n) for n in point)):
                raise ValueError(f"Invalid motion landmark {key}.")
        for key, path in paths.items():
            path.append([a-b for a, b in zip(pose[key], pose["anchor"])])
    return paths


def motion_work_check(poses):
    """Return travel-weighted mean kgf/kg for the tracked hand and handle cap."""
    paths = registered_paths(poses, ("plates", "hand", "handle_cap"))
    rise = paths["plates"][0][1] - paths["plates"][-1][1]
    if rise <= 0:
        raise ValueError("Place the frames in plate-lifting order.")
    result = {"plate_rise_px": rise}
    for key in ("hand", "handle_cap"):
        travel = sum(dist(a, b) for a, b in pairwise(paths[key]))
        if travel <= 0:
            raise ValueError(f"The {key} did not move.")
        result[f"{key}_path_px"] = travel
        result[f"{key}_kgf_per_kg"] = rise / travel
    return result


def motion_intervals(poses):
    """Projected work per unit contact travel over each observed interval."""
    paths = registered_paths(poses, ("plates", "near_hand", "far_hand"))
    midpoints = [[(a + b) / 2 for a, b in zip(near, far)]
                 for near, far in zip(paths["near_hand"], paths["far_hand"])]
    distances = [dist(a, b) for a, b in pairwise(midpoints)]
    rises = [a[1] - b[1] for a, b in pairwise(paths["plates"])]
    if min(distances) <= 0 or min(rises) < 0 or sum(rises) <= 0:
        raise ValueError("Each interval needs moving hands and ascending or level plates.")
    travel = sum(distances)
    knots = [round(s / travel, 12) for s in accumulate(distances, initial=0.0)]
    # Matching summation at the endpoint also handles platform rounding differences.
    knots[-1] = 1.0
    curve = dict(type="interval_mean", input="stroke_fraction", domain=[0, 1],
                 output="kgf_per_kg", knots=knots,
                 coefficients=[[round(h / s, 12)] for h, s in zip(rises, distances)])
    return dict(resistance_curve=curve, plate_rise_px=sum(rises), hand_path_px=travel,
                mean_kgf_per_kg=sum(rises)/travel)
