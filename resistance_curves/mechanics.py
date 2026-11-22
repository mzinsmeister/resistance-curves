"""Planar, quasi-static mechanics. Points use image coordinates (y down)."""

from math import asin, atan2, cos, degrees, dist, hypot, isfinite, radians, remainder

from .curves import fit_curve

G = 9.80665
FIELDS = {
    "lever": ("pivot", "plates", "grip"),
    "belt_cam": ("pivot", "plates", "belt_load", "belt_cam", "cam_pivot", "grip"),
    "sled": ("rail_low", "rail_high"),
}


def vector(start, end):
    return end[0] - start[0], end[1] - start[1]


def direction(start, end):
    dx, dy = vector(start, end)
    if hypot(dx, dy) < 5:
        raise ValueError("Landmarks less than 5 pixels apart cannot establish a direction.")
    return degrees(atan2(dy, dx))


def moment_arm(pivot, start, end):
    """Signed perpendicular distance to the oriented line start -> end."""
    dx, dy = vector(start, end)
    direction(start, end)
    rx, ry = vector(pivot, start)
    return (rx * dy - ry * dx) / hypot(dx, dy)


def tangential_force(tension, cam_arm, grip_radius):
    """Cam output in the input force unit, using a common length unit."""
    if grip_radius <= 0:
        raise ValueError("Grip radius must be positive.")
    return tension * abs(cam_arm) / grip_radius


def _measure(kind, points, rail_3d=None, up="y"):
    if kind == "sled":
        if rail_3d is not None:
            low, high = rail_3d["rail_low"], rail_3d["rail_high"]
            vertical = "xyz".index(up[-1])
            rise = (high[vertical] - low[vertical]) * (-1 if up.startswith("-") else 1)
            length = dist(low, high)
            if length <= 0 or rise < 0:
                raise ValueError("Check the direction of the 3D rail landmarks.")
            ratio = rise / length
            return {"force_ratio": ratio, "rail_inclination_deg": degrees(asin(min(1, ratio)))}
        direction(points["rail_low"], points["rail_high"])
        rise = points["rail_low"][1] - points["rail_high"][1]
        if rise < 0:
            raise ValueError("rail_low must be at or below rail_high.")
        length = dist(points["rail_low"], points["rail_high"])
        return {"rail_inclination_deg": degrees(atan2(rise, abs(points["rail_high"][0] - points["rail_low"][0]))),
                "force_ratio": rise / length}

    pivot, plates, grip = (points[k] for k in ("pivot", "plates", "grip"))
    axis = points.get("cam_pivot", pivot)
    grip_angle = direction(axis, grip)
    load_angle = direction(pivot, plates)
    radius = dist(axis, grip)
    gravity_arm = plates[0] - pivot[0]
    result = {"grip_angle_deg": grip_angle, "load_angle_deg": load_angle,
              "gravity_arm_px": gravity_arm, "grip_radius_px": radius}
    if kind == "lever":
        result.update(radius_ratio=dist(pivot, plates) / radius, force_ratio=abs(gravity_arm) / radius)
    else:
        start, end = points["belt_load"], points["belt_cam"]
        load_arm = moment_arm(pivot, start, end)
        cam_arm = moment_arm(axis, start, end)
        if abs(load_arm) < 5:
            raise ValueError("Load-side belt moment arm is too small to resolve.")
        tension_ratio = -gravity_arm / load_arm
        if tension_ratio < 0:
            raise ValueError("These landmarks would require the belt to push. Check the belt span and pivots.")
        result.update(load_belt_arm_px=load_arm, cam_belt_arm_px=cam_arm,
                      tension_per_plate_weight=tension_ratio,
                      force_ratio=tangential_force(tension_ratio, cam_arm, radius))
    return result


def _points(pose, kind):
    if not isinstance(pose, dict):
        raise ValueError("Each pose must contain named landmark coordinates.")
    points = {}
    for field in FIELDS[kind]:
        pair = pose.get(field)
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2 and
                all(type(n) in (int, float) and 0 <= n <= 1000 for n in pair)):
            raise ValueError(f"Expected {field} as [x, y] on the 1000-pixel square.")
        points[field] = pair
    return points


def estimate(observation, plate_kg=None):
    """Estimate contact force magnitude over the observed stroke, ordered start to finish."""
    if plate_kg is not None and (not isfinite(plate_kg) or plate_kg < 0):
        raise ValueError("Plate mass must be finite and nonnegative.")
    if not isinstance(observation, dict):
        raise ValueError("Expected a JSON object.")
    kind = observation.get("mechanism")
    if kind == "unresolved":
        raise ValueError(f"Insufficient evidence. {observation.get('evidence', '')}")
    if not isinstance(kind, str) or kind not in FIELDS:
        raise ValueError("Unknown mechanism.")
    poses = observation.get("poses")
    static_model = bool(observation.get("model_source")) and isinstance(poses, list) and len(poses) == 1
    sweep = observation.get("sweep_deg")
    if sweep is not None and not (static_model and kind == "lever"):
        raise ValueError("A declared sweep is only valid for a single rigid lever model.")
    if static_model and kind == "lever":
        if type(sweep) not in (float, int) or not 1 <= abs(sweep) < 175:
            raise ValueError("A static lever requires an evidenced signed sweep_deg (1 to <175 degrees).")
    if not isinstance(poses, list) or not poses or (len(poses) < 2 and not (static_model and kind in ("lever", "sled"))):
        raise ValueError("Supply at least two poses in movement order.")
    model = observation.get("model_source", {})
    metric_poses = model.get("world_m", [None] * len(poses))
    if len(metric_poses) != len(poses):
        raise ValueError("Each model pose requires its own metric landmarks.")
    measured = [_measure(kind, _points(p, kind), metric, model.get("up", "y"))
                for p, metric in zip(poses, metric_poses)]
    if any("joint" in pose for pose in poses):
        from .anatomy import joint_geometry

        if kind == "sled":
            raise ValueError("Rotary joint geometry requires a lever or belt cam.")
        axis = "cam_pivot" if kind == "belt_cam" else "pivot"
        for pose, measurement in zip(poses, measured):
            measurement.update(joint_geometry(pose, axis))
    if kind == "sled":
        inclines = [m["rail_inclination_deg"] for m in measured]
        if max(inclines) - min(inclines) > 5:
            raise ValueError("Rail inclinations disagree by over 5 degrees. Check camera alignment.")
        ratio = sum(m["force_ratio"] for m in measured) / len(measured)
        curve = [(0, ratio), (100, ratio)]
    else:
        angles = [m["grip_angle_deg"] for m in measured]
        travel = [0.0]
        for a, b in zip(angles, angles[1:]):
            step = remainder(b - a, 360)
            if abs(step) < 1 or abs(step) >= 175 or travel[-1] * step < 0:
                raise ValueError("Grip positions must progress in one direction with an unambiguous sweep.")
            travel.append(travel[-1] + step)
        if static_model:
            travel.append(sweep)
        for m, position in zip(measured, travel):
            m["travel_pct"] = (position / travel[-1]) * 100
        curve = [(m["travel_pct"], m["force_ratio"]) for m in measured]
        if kind == "lever":
            ratios = [m["radius_ratio"] for m in measured]
            offsets = [m["load_angle_deg"] - m["grip_angle_deg"] for m in measured]
            if max(ratios) > 1.15 * min(ratios) or any(abs(remainder(o - offsets[0], 360)) > 8 for o in offsets):
                raise ValueError("Landmarks disagree with one rigid lever. Check projection and pivot selection.")
            ratio = sum(ratios) / len(ratios)
            start = measured[0]["load_angle_deg"]
            curve = [(i, ratio * abs(cos(radians(start + travel[-1] * i / 100)))) for i in range(101)]
    if plate_kg is not None:
        for m in measured:
            m["contact_force_kgf"] = m["force_ratio"] * plate_kg
            m["contact_force_N"] = m["contact_force_kgf"] * G
            if kind == "belt_cam":
                m["belt_tension_N"] = m["tension_per_plate_weight"] * plate_kg * G
    samples = []
    for pct, ratio in curve:
        sample = {"travel_pct": pct, "newtons_per_kg": ratio * G}
        if plate_kg is not None:
            sample["force_kgf"] = ratio * plate_kg
            sample["force_N"] = sample["force_kgf"] * G
        samples.append(sample)
    return {"mechanism": kind, "evidence": observation.get("evidence", ""), "plate_kg": plate_kg,
            "poses": measured, "samples": samples,
            "resistance_curve": fit_curve([(pct / 100, ratio) for pct, ratio in curve])}
