"""Map a tangential rotary contact force to its external joint moment arm."""

from math import acos, degrees, dist, hypot, isfinite

from .mechanics import moment_arm, vector

LANDMARKS = ("joint", "proximal", "distal", "scale_start", "scale_end")


def joint_geometry(pose, axis_key):
    for name in LANDMARKS:
        point = pose.get(name)
        if not (isinstance(point, list) and len(point) == 2 and
                all(type(x) in (float, int) and 0 <= x <= 1000 for x in point)):
            raise ValueError(f"Missing or invalid anatomical landmark {name}.")
    length = pose.get("scale_m")
    if type(length) not in (float, int) or not isfinite(length) or length <= 0 or not pose.get("scale_source"):
        raise ValueError("Supply a positive scale_m and document scale_source.")
    span = dist(pose["scale_start"], pose["scale_end"])
    u, v = (vector(pose["joint"], pose[key]) for key in ("proximal", "distal"))
    if min(span, hypot(*u), hypot(*v)) < 5:
        raise ValueError("Anatomical landmarks or scale reference too close to resolve.")
    cos_angle = sum(a * b for a, b in zip(u, v)) / (hypot(*u) * hypot(*v))
    angle = 180 - degrees(acos(max(-1, min(1, cos_angle))))
    if "pull_toward" in pose:
        # Exact perpendicular distance from joint center to the line of action grip -> pull_toward.
        arm = abs(moment_arm(pose["joint"], pose["grip"], pose["pull_toward"]))
    else:
        radial = vector(pose[axis_key], pose["grip"])
        contact = vector(pose["joint"], pose["grip"])
        # Perpendicular distance to the tangent equals the radial projection.
        arm = abs(sum(a * b for a, b in zip(radial, contact))) / hypot(*radial)
    return {"angle_deg": angle, "joint_arm_m": arm * length / span}
