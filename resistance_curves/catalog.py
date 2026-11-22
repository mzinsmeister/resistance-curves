"""Convert versioned machine records to the static site's view model."""

from math import isfinite
from .work_check import motion_work_check
from .curves import fit_curve
from .mechanics import estimate, G


def number(value, low, high=float("inf")):
    return type(value) in (float, int) and isfinite(value) and low <= value <= high


def check_pairs(points, y_min, x_max):
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("Expected at least two ordered coordinate pairs.")
    prev = -1
    for pair in points:
        if not (isinstance(pair, list) and len(pair) == 2 and number(pair[0], 0, x_max)
                and number(pair[1], y_min) and prev < pair[0]):
            raise ValueError("Invalid coordinate or unordered curve.")
        prev = pair[0]


def machine_view(record):
    for key in ("name", "manufacturer", "source", "kind", "movement"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Missing machine field {key}.")
    mass = record.get("plate_kg")
    if not number(mass, 0.000001):
        raise ValueError("plate_kg must be positive.")
    view = {key: record[key] for key in ("name", "manufacturer", "source", "kind", "movement", "plate_kg")}
    if ("observation" in record) == ("reference_kgf" in record):
        raise ValueError("Choose a photo observation or a reported force curve.")
    geometry = []
    if "observation" in record:
        profile = estimate(record["observation"], mass)
        view["mechanism"] = profile["mechanism"]
        if "model_source" in record["observation"]:
            view["model_origin"] = record["observation"]["model_source"]["source"]
            view["model_evidence"] = record["observation"]["evidence"]
        points = [[s["travel_pct"], s["force_kgf"]] for s in profile["samples"]]
        for p in profile["poses"]:
            if "angle_deg" in p:
                geometry.append([p["travel_pct"], p["angle_deg"], p["joint_arm_m"]])
    else:
        points = record["reference_kgf"]
        view["mechanism"] = "reported"
        includes_base = record.get("reference_includes_base", True)
        if type(includes_base) is not bool:
            raise ValueError("reference_includes_base must be a JSON boolean.")
        view["reference_includes_base"] = includes_base
    check_pairs(points, 0, 100)
    if points[0][0] != 0 or points[-1][0] != 100:
        raise ValueError("Travel must span 0 to 100 percent.")
    if geometry:
        angles = [row[1] for row in geometry]
        if not (all(a < b for a, b in zip(angles, angles[1:])) or
                all(a > b for a, b in zip(angles, angles[1:]))):
            raise ValueError("Joint angle must progress monotonically through the lifting stroke.")
    if "observation" in record:
        curve = profile["resistance_curve"]
    else:
        curve = fit_curve([(pct / 100, force / mass) for pct, force in points])
    if "resistance_curve" in record and record["resistance_curve"] != curve:
        raise ValueError("Stored curve differs from the source. Refresh it with the fit command.")
    view.update(resistance_curve=curve, points=points, geometry=geometry, gravity=G)
    if "base_resistance" in record:
        base = record["base_resistance"]
        if not isinstance(base, dict) or not number(base.get("starting_kgf"), 0) or not base.get("source"):
            raise ValueError("Base resistance needs nonnegative starting_kgf and a source.")
        if "finish_kgf" in base and not number(base["finish_kgf"], 0):
            raise ValueError("finish_kgf must be finite and nonnegative.")
        view["base_resistance"] = base
    if "motion_check" in record:
        check = record["motion_check"]
        view["motion_check"] = dict(motion_work_check(check["poses"]), url=check["url"],
                                    uncertainty=check["uncertainty"])
    return view
