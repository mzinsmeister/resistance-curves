"""Prepare consistent square views for automatic or human-reviewed landmark extraction."""

from PIL import Image, ImageOps

PROMPT = """Inspect these ordered, level side views of one plate-loaded machine at successive positions.
Trace the load path before choosing a model. Return one JSON object with mechanism, evidence (a string
explaining what is visible, assumptions and sources of error), and poses (one object per image in order).
Use absolute [x,y] coordinates on each provided 1000 by 1000 padded image. Origin is top left.
Do not infer mass, use published resistance values, or calculate force. Identify the SAME moving parts throughout.
lever: one rigid rotating arm. Each pose needs pivot (fixed axle center), plates (center of mass
of the actual stacked plates at their hub midpoint — NEVER the tip or middle of an empty protruding loading pin), and grip (center of hand/pad contact on that arm).
For a chain pulling directly on a rigid lever, place grip at the chain anchor and supply pull_toward
at a second point along the taut line toward the lifter. If two distinct stations carry plates on the
same lever, mark secondary_plates at the second stack's hub and record secondary_plate_fraction
(the fraction of total modeled plate mass at that station) at the observation level.
belt_cam: two fixed axles coupled by one taut, directly connecting belt span. Each pose needs pivot
(load axle), plates, belt_load and belt_cam (two distinct points ON THE SAME straight belt span,
ordered from load side toward hand side), cam_pivot (output axle), grip (rigid output contact or
handle-mount pin on the cam arm; if a handle yoke pivots freely on that pin, place grip at the
rigid mounting pin and supply pull_toward at the hand contact).
Use the straight line tangent to the cam, not the outer cam radius. Check that belt tension lifts the load.
sled: plates and contact surface translate together along one straight fixed rail. Use rail_low and rail_high
(two widely separated points on its centerline, ordered low to high). Exclude leg presses with moving seats
unless the added plates and user contact actually move together.
If linkage, belt routing, gravity direction, changing camera side, moving pivots, plate center or grip
are unclear, or photos show the same pose on a rotating machine, return mechanism "unresolved", poses [],
and explain which specific view or landmark is needed. Reject oblique views, independent unseen load paths,
multi-link, idler-routed and variable-gearing devices outside the models above. For a rotary isolation exercise where the opposing contact force is tangential, optionally add to EVERY pose:
joint, proximal, distal (joint axis, proximal and distal segment landmarks in the motion plane; full extension = 0 degrees),
scale_start and scale_end (endpoints of an in-plane length reference), scale_m (positive length in meters),
and scale_source (how it was measured or estimated). If no defensible metric reference or visible joint exists,
omit these fields and keep a force-only analysis. Review the overlays before recording the result. No markdown."""


def prepare(paths, folder):
    if len(paths) < 2:
        raise ValueError("Supply two or more photos in movement order.")
    folder.mkdir(parents=True, exist_ok=False)
    views = []
    for index, path in enumerate(paths, 1):
        with Image.open(path) as source:
            upright = ImageOps.exif_transpose(source).convert("RGB")
            square = ImageOps.pad(upright, (1000, 1000), color="white")
            view = folder / f"pose-{index:03}.jpg"
            square.save(view, quality=94)
            views.append(view)
    (folder / "prompt.txt").write_text(PROMPT)
    return views
