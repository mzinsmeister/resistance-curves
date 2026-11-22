"""Cross-check a plate-induced force estimate from clean side-view motion frames."""

from math import dist, isfinite


def motion_work_check(poses):
    """Return travel-weighted mean kgf/kg for the tracked hand and handle cap."""
    if not isinstance(poses, list) or len(poses) < 2:
        raise ValueError("A work check needs two or more ordered frames.")
    paths = {key: [] for key in ("plates", "hand", "handle_cap")}
    for pose in poses:
        for key in ("anchor", *paths):
            point = pose.get(key)
            if not (isinstance(point, list) and len(point) == 2 and
                    all(type(n) in (int, float) and isfinite(n) for n in point)):
                raise ValueError(f"Invalid work-check landmark {key}.")
        for key, path in paths.items():
            path.append([a-b for a, b in zip(pose[key], pose["anchor"])])
    rise = paths["plates"][0][1] - paths["plates"][-1][1]
    if rise <= 0:
        raise ValueError("Place the frames in plate-lifting order.")
    result = {"plate_rise_px": rise}
    for key in ("hand", "handle_cap"):
        travel = sum(dist(a, b) for a, b in zip(paths[key], paths[key][1:]))
        if travel <= 0:
            raise ValueError(f"The {key} did not move.")
        result[f"{key}_path_px"] = travel
        result[f"{key}_kgf_per_kg"] = rise / travel
    return result
