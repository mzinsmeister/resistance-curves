"""Static force plots and collision-free annotated force-diagram overlays."""

from math import atan2, cos, degrees, dist, hypot, pi, sin
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.patheffects as pe
import numpy as np
from PIL import Image

from .anatomy import LANDMARKS
from .curves import evaluate_curve
from .mechanics import FIELDS, moment_arm


# High-contrast, colorblind-friendly engineering palette for force diagrams.
C_LOAD = "#38bdf8"     # Sky cyan: load arm, plates, gravity
C_LOAD_TXT = "#0284c7" # Deeper cyan for white pill text readability
C_OUT = "#f59e0b"      # Amber: output/contact arm, contact force
C_OUT_TXT = "#b45309"  # Deeper amber for white pill text
C_BELT = "#ec4899"     # Magenta: taut belt span & belt moment arms
C_PIVOT = "#ef4444"    # Crimson: fixed axles / pivots
C_PIVOT_TXT = "#dc2626"
C_ANAT = "#10b981"     # Emerald: anatomical joint & limb segments
C_ANAT_TXT = "#047857"
C_SCALE = "#8b5cf6"    # Violet: metric reference scale bar

HALO = [pe.Stroke(linewidth=5.2, foreground="#0f172a", alpha=0.72), pe.Normal()]
HALO_THIN = [pe.Stroke(linewidth=3.4, foreground="#0f172a", alpha=0.68), pe.Normal()]


def _unit(dx, dy):
    length = hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0
    return dx / length, dy / length


def _project_on_line(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    denom = dx * dx + dy * dy
    if denom < 1e-9:
        return start
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denom
    return (start[0] + t * dx, start[1] + t * dy)


def _detect_viewport(photo_arr, active_points):
    """Trim pure-white letterbox margins and gently zoom if landmarks are tightly clustered."""
    h, w = photo_arr.shape[:2]
    # Detect non-white rows/cols (ImageOps.pad fills with 255)
    non_white = (photo_arr < 248).any(axis=2)
    rows = np.where(non_white.any(axis=1))[0]
    cols = np.where(non_white.any(axis=0))[0]
    if len(rows) > 40 and len(cols) > 40:
        y0, y1 = float(rows[0]) * 1000.0 / h, float(rows[-1] + 1) * 1000.0 / h
        x0, x1 = float(cols[0]) * 1000.0 / w, float(cols[-1] + 1) * 1000.0 / w
    else:
        x0, y0, x1, y1 = 0.0, 0.0, 1000.0, 1000.0

    # Ensure every active point stays comfortably inside the crop
    if active_points:
        pxs = [p[0] for p in active_points]
        pys = [p[1] for p in active_points]
        lx0, lx1 = min(pxs), max(pxs)
        ly0, ly1 = min(pys), max(pys)
        x0 = min(x0, max(0.0, lx0 - 65))
        x1 = max(x1, min(1000.0, lx1 + 65))
        y0 = min(y0, max(0.0, ly0 - 65))
        y1 = max(y1, min(1000.0, ly1 + 65))

        # Gently zoom in on wide shots where the mechanism fills <48% of the photo width
        vw, vh = x1 - x0, y1 - y0
        lw, lh = lx1 - lx0, ly1 - ly0
        if lw < 0.44 * vw and lh < 0.56 * vh and vw > 550:
            cx, cy = (lx0 + lx1) / 2.0, (ly0 + ly1) / 2.0
            target_span = max(lw * 2.55, lh * 2.15, 480.0)
            target_w = min(vw, max(target_span, 520.0))
            target_h = min(vh, max(target_span * (vh / vw), 440.0))
            nx0 = max(x0, min(x1 - target_w, cx - target_w / 2.0))
            ny0 = max(y0, min(y1 - target_h, cy - target_h / 2.0))
            x0, x1 = nx0, nx0 + target_w
            y0, y1 = ny0, ny0 + target_h

    return x0, x1, y0, y1


def _box_overlap_area(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _point_to_seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom < 1e-9:
        return hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / denom))
    return hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def _place_labels(ax, items, segments, dots, viewport, hud_boxes):
    """Place non-overlapping label pills radially outward from mechanism with leader lines."""
    x0, x1, y0, y1 = viewport
    vw, vh = x1 - x0, y1 - y0
    span = min(vw, vh)
    margin_x, margin_y = vw * 0.025, vh * 0.032

    if dots:
        cx = sum(p[0] for p in dots) / len(dots)
        cy = sum(p[1] for p in dots) / len(dots)
    else:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

    placed = list(hud_boxes)
    char_w = vw * 0.0112
    pad_w = vw * 0.026
    box_h = vh * 0.044

    # 16 candidate directions around the clock
    angles = [2.0 * pi * k / 16.0 for k in range(16)]
    radii = [span * f for f in (0.075, 0.115, 0.16, 0.21, 0.27)]

    for item in items:
        ax_pt = item["point"]
        text = item["text"]
        color = item["color"]
        pref = item.get("prefer")

        bw = max(vw * 0.055, len(text) * char_w + pad_w)
        bh = box_h

        # Preferred outward vector away from mechanism center
        if pref is not None:
            ux, uy = _unit(pref[0], pref[1])
        else:
            ux, uy = _unit(ax_pt[0] - cx, ax_pt[1] - cy)
            if ux == 0.0 and uy == 0.0:
                ux, uy = 1.0, -0.5

        best_score = float("inf")
        best_center = (ax_pt[0] + ux * span * 0.09, ax_pt[1] + uy * span * 0.09)

        for r in radii:
            for ang in angles:
                dx, dy = cos(ang), sin(ang)
                # Offset box center so edge clears the anchor cleanly
                bx = ax_pt[0] + dx * (r + bw * 0.35)
                by = ax_pt[1] + dy * (r + bh * 0.45)
                box = (bx - bw / 2.0, by - bh / 2.0, bx + bw / 2.0, by + bh / 2.0)

                score = 0.0
                # Stay strictly inside visible image bounds
                if box[0] < x0 + margin_x:
                    score += 50000.0 + (x0 + margin_x - box[0]) * 500.0
                if box[2] > x1 - margin_x:
                    score += 50000.0 + (box[2] - (x1 - margin_x)) * 500.0
                if box[1] < y0 + margin_y:
                    score += 50000.0 + (y0 + margin_y - box[1]) * 500.0
                if box[3] > y1 - margin_y:
                    score += 50000.0 + (box[3] - (y1 - margin_y)) * 500.0

                # Hard penalty against overlapping any existing label or HUD pill (with breathing gap)
                pad_gap_x, pad_gap_y = vw * 0.010, vh * 0.012
                padded = (box[0] - pad_gap_x, box[1] - pad_gap_y, box[2] + pad_gap_x, box[3] + pad_gap_y)
                for other in placed:
                    area = _box_overlap_area(padded, other)
                    if area > 0.0:
                        score += 20000.0 + area * 8.0

                # Penalize covering landmark dots
                for d in dots:
                    if box[0] - vw * 0.018 <= d[0] <= box[2] + vw * 0.018 and box[1] - vh * 0.018 <= d[1] <= box[3] + vh * 0.018:
                        score += 1800.0

                # Penalize sitting directly on top of force lines
                for s0, s1 in segments:
                    d_seg = _point_to_seg_dist(bx, by, s0, s1)
                    if d_seg < min(bw, bh) * 0.58:
                        score += (min(bw, bh) * 0.58 - d_seg) * 14.0

                # Gentle preference for outward direction & reasonable proximity
                align = dx * ux + dy * uy
                score += (1.0 - align) * 28.0
                score += (r / span) * 180.0

                if score < best_score:
                    best_score = score
                    best_center = (bx, by)

        bx, by = best_center
        final_box = (bx - bw / 2.0, by - bh / 2.0, bx + bw / 2.0, by + bh / 2.0)
        placed.append(final_box)

        # Draw crisp leader line from pill center to exact anchor point
        if hypot(bx - ax_pt[0], by - ax_pt[1]) > span * 0.035:
            ax.plot(
                [ax_pt[0], bx], [ax_pt[1], by],
                color="#ffffff", lw=2.3, alpha=0.85, zorder=9, solid_capstyle="round",
            )
            ax.plot(
                [ax_pt[0], bx], [ax_pt[1], by],
                color=color, lw=1.15, alpha=0.95, zorder=9.5, solid_capstyle="round",
            )

        ax.text(
            bx, by, text,
            fontsize=8.6, fontweight="bold", color=color,
            va="center", ha="center", zorder=11,
            bbox={
                "facecolor": "#ffffff", "alpha": 0.94, "edgecolor": color,
                "linewidth": 1.15, "boxstyle": "round,pad=0.28",
            },
        )


def _arrow(ax, start, end, color, lw=3.0, ms=16, zorder=6):
    # Dark halo underneath for readability on light or dark photos
    bg = FancyArrowPatch(
        start, end,
        arrowstyle=f"-|>,head_length={ms * 0.58},head_width={ms * 0.36}",
        color="#0f172a", alpha=0.65, linewidth=lw + 2.2, zorder=zorder - 0.1, mutation_scale=1.0,
    )
    fg = FancyArrowPatch(
        start, end,
        arrowstyle=f"-|>,head_length={ms * 0.55},head_width={ms * 0.34}",
        color=color, linewidth=lw, zorder=zorder, mutation_scale=1.0,
    )
    ax.add_patch(bg)
    ax.add_patch(fg)


def draw_force_diagram(pose, mechanism, view_path, out_path, *,
                       pose_index=None, pose_meta=None, jpeg_quality=88):
    """Render a clean, collision-free free-body / force diagram over a prepared pose image."""
    photo_arr = None
    if view_path is not None and Path(view_path).is_file():
        with Image.open(view_path) as photo:
            photo_arr = np.asarray(photo.convert("RGB"))

    # Collect geometry first to compute smart viewport
    segments = []
    dots = []
    labels = []

    if mechanism == "sled":
        low, high = pose["rail_low"], pose["rail_high"]
        active = [low, high]
    elif mechanism in ("lever", "belt_cam"):
        pivot = pose["pivot"]
        plates_math = pose["plates"]
        grip = pose["grip"]
        axis = pose.get("cam_pivot", pivot)
        # If an oblique view stores the visible plate center separately from its grip-plane
        # projection, draw the load arm in the visible plate plane connected by the axle shaft.
        if mechanism == "lever" and "observed_plate_center" in pose:
            plates_vis = pose["observed_plate_center"]
            plate_pivot = [
                pivot[0] + (plates_vis[0] - plates_math[0]),
                pivot[1] + (plates_vis[1] - plates_math[1]),
            ]
        else:
            plates_vis = plates_math
            plate_pivot = pivot
        active = [pivot, plate_pivot, plates_vis, grip, axis]
        if mechanism == "belt_cam":
            active.extend([pose["belt_load"], pose["belt_cam"]])
    else:
        active = []

    for k in ("joint", "proximal", "distal"):
        if k in pose:
            active.append(pose[k])

    if photo_arr is not None:
        x0, x1, y0, y1 = _detect_viewport(photo_arr, active)
    else:
        x0, x1, y0, y1 = 0.0, 1000.0, 0.0, 1000.0

    vw, vh = x1 - x0, y1 - y0
    span = min(vw, vh)
    aspect = vw / max(vh, 1.0)
    fig_w = 7.6
    fig_h = max(4.4, min(7.6, fig_w / max(aspect, 0.65)))
    fig = Figure(figsize=(fig_w, fig_h), dpi=125)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])

    if photo_arr is not None:
        ax.imshow(photo_arr, extent=(0, 1000, 1000, 0))
    else:
        ax.set_facecolor("#f3f6f5")
        for g in range(100, 1000, 100):
            ax.axhline(g, color="#dce4e1", lw=0.7, zorder=0)
            ax.axvline(g, color="#dce4e1", lw=0.7, zorder=0)

    arrow_len = span * 0.155

    if mechanism == "sled":
        low, high = pose["rail_low"], pose["rail_high"]
        corner = (high[0], low[1])
        ax.plot([low[0], corner[0]], [low[1], corner[1]],
                color=C_LOAD, ls="--", lw=2.0, alpha=0.9, zorder=3, path_effects=HALO_THIN)
        ax.plot([corner[0], high[0]], [corner[1], high[1]],
                color=C_LOAD, ls="--", lw=2.0, alpha=0.9, zorder=3, path_effects=HALO_THIN)
        _arrow(ax, low, high, C_OUT, lw=3.2, ms=18, zorder=5)
        mid = ((low[0] + high[0]) / 2.0, (low[1] + high[1]) / 2.0)
        g_end = (mid[0], min(y1 - vh * 0.06, mid[1] + arrow_len * 1.15))
        _arrow(ax, mid, g_end, C_LOAD, lw=3.0, ms=16, zorder=6)
        ux, uy = _unit(high[0] - low[0], high[1] - low[1])
        f_end = (mid[0] + ux * arrow_len * 1.15, mid[1] + uy * arrow_len * 1.15)
        _arrow(ax, mid, f_end, C_OUT, lw=3.2, ms=17, zorder=7)
        ax.scatter([low[0], high[0]], [low[1], high[1]],
                   color=C_PIVOT, edgecolor="white", linewidth=1.8, s=75, zorder=8)
        rise = low[1] - high[1]
        run = abs(high[0] - low[0])
        ang = degrees(atan2(rise, run)) if run or rise else 0.0
        segments.extend([(low, high), (low, corner), (corner, high), (mid, g_end)])
        dots.extend([low, high, mid, g_end, f_end])
        labels.extend([
            {"point": low, "text": "Rail low", "color": C_PIVOT_TXT},
            {"point": high, "text": "Rail high", "color": C_PIVOT_TXT},
            {"point": g_end, "text": "Mg", "color": C_LOAD_TXT, "prefer": (0.2, 1.0)},
            {"point": f_end, "text": "F = Mg sin θ", "color": C_OUT_TXT, "prefer": (-0.6, -0.8)},
            {"point": (corner[0], (low[1] + high[1]) / 2.0), "text": f"θ = {ang:.1f}°", "color": C_LOAD_TXT, "prefer": (1.0, 0.0)},
        ])

    elif mechanism in ("lever", "belt_cam"):
        # Optional shaft line when visible plate plane is offset laterally from grip plane
        offset_plane = (mechanism == "lever" and "observed_plate_center" in pose
                        and dist(pivot, plate_pivot) > 8)
        if offset_plane:
            ax.plot([pivot[0], plate_pivot[0]], [pivot[1], plate_pivot[1]],
                    color=C_PIVOT, ls="--", lw=2.2, zorder=3.5, path_effects=HALO_THIN)
            segments.append((pivot, plate_pivot))

        # Horizontal gravity moment arm from plate pivot to plate plumb line
        plumb_pt = (plates_vis[0], plate_pivot[1])
        ax.plot([plate_pivot[0], plumb_pt[0]], [plate_pivot[1], plumb_pt[1]],
                color=C_LOAD, ls="--", lw=2.0, alpha=0.92, zorder=3, path_effects=HALO_THIN)
        ax.plot([plates_vis[0], plumb_pt[0]], [plates_vis[1], plumb_pt[1]],
                color=C_LOAD, ls=":", lw=1.8, alpha=0.8, zorder=3)
        # Load lever arm
        ax.plot([plate_pivot[0], plates_vis[0]], [plate_pivot[1], plates_vis[1]],
                color=C_LOAD, lw=3.2, zorder=4, path_effects=HALO)
        # Gravity vector downward at plates
        g_len = min(arrow_len, max(span * 0.09, y1 - vh * 0.07 - plates_vis[1]))
        g_end = (plates_vis[0], min(y1 - vh * 0.05, plates_vis[1] + g_len))
        _arrow(ax, plates_vis, g_end, C_LOAD, lw=3.0, ms=16, zorder=6)

        # Output arm (axis -> grip)
        ax.plot([axis[0], grip[0]], [axis[1], grip[1]],
                color=C_OUT, lw=3.2, zorder=4, path_effects=HALO)

        # Exact physics direction for lifter's tangential contact force opposing gravity
        rx, ry = grip[0] - axis[0], grip[1] - axis[1]
        tx, ty = _unit(-ry, rx)  # clockwise unit tangent in y-down coords
        if mechanism == "lever":
            grav_sign = 1.0 if (plates_math[0] - pivot[0]) >= 0 else -1.0
            lift_sign = -grav_sign
        else:
            # Belt tension pulls the cam from belt_cam toward belt_load (opposite belt_load -> belt_cam),
            # so opposing belt tension requires torque with the SAME sign as moment_arm(axis, belt_load, belt_cam).
            cam_arm = moment_arm(axis, pose["belt_load"], pose["belt_cam"])
            lift_sign = 1.0 if cam_arm >= 0 else -1.0
        fx, fy = tx * lift_sign, ty * lift_sign
        f_end = (
            max(x0 + vw * 0.05, min(x1 - vw * 0.05, grip[0] + fx * arrow_len)),
            max(y0 + vh * 0.05, min(y1 - vh * 0.05, grip[1] + fy * arrow_len)),
        )
        _arrow(ax, grip, f_end, C_OUT, lw=3.0, ms=16, zorder=6)

        segments.extend([
            (plate_pivot, plates_vis), (plate_pivot, plumb_pt), (plates_vis, g_end),
            (axis, grip), (grip, f_end),
        ])

        if mechanism == "belt_cam":
            bl, bc = pose["belt_load"], pose["belt_cam"]
            ax.plot([bl[0], bc[0]], [bl[1], bc[1]],
                    color=C_BELT, lw=3.2, zorder=5, path_effects=HALO)
            bmid = ((bl[0] + bc[0]) / 2.0, (bl[1] + bc[1]) / 2.0)
            bux, buy = _unit(bc[0] - bl[0], bc[1] - bl[1])
            _arrow(ax, (bmid[0] - bux * span * 0.04, bmid[1] - buy * span * 0.04),
                   (bmid[0] + bux * span * 0.04, bmid[1] + buy * span * 0.04),
                   C_BELT, lw=3.0, ms=15, zorder=7)
            p_proj = _project_on_line(pivot, bl, bc)
            c_proj = _project_on_line(axis, bl, bc)
            ax.plot([pivot[0], p_proj[0]], [pivot[1], p_proj[1]],
                    color=C_BELT, ls="--", lw=1.9, alpha=0.9, zorder=4, path_effects=HALO_THIN)
            ax.plot([axis[0], c_proj[0]], [axis[1], c_proj[1]],
                    color=C_BELT, ls="--", lw=1.9, alpha=0.9, zorder=4, path_effects=HALO_THIN)
            ax.scatter([bl[0], bc[0]], [bl[1], bc[1]],
                       color=C_BELT, edgecolor="white", linewidth=1.4, s=55, zorder=8)
            segments.extend([(bl, bc), (pivot, p_proj), (axis, c_proj)])
            dots.extend([bl, bc, bmid])
            labels.append({"point": bmid, "text": "Belt T", "color": C_BELT})

        # Landmark dots
        ax.scatter([pivot[0]], [pivot[1]], color=C_PIVOT, edgecolor="white", linewidth=1.8, s=86, zorder=9)
        if offset_plane:
            ax.scatter([plate_pivot[0]], [plate_pivot[1]], color=C_PIVOT, edgecolor="white", linewidth=1.5, s=62, zorder=9)
            dots.append(plate_pivot)
        if mechanism == "belt_cam":
            ax.scatter([axis[0]], [axis[1]], color=C_PIVOT, edgecolor="white", linewidth=1.8, s=86, zorder=9)
            dots.append(axis)
        ax.scatter([plates_vis[0]], [plates_vis[1]], color=C_LOAD, edgecolor="white", linewidth=1.7, s=74, zorder=9)
        ax.scatter([grip[0]], [grip[1]], color=C_OUT, edgecolor="white", linewidth=1.7, s=74, zorder=9)

        dots.extend([pivot, plates_vis, grip, g_end, f_end])
        labels.extend([
            {"point": pivot, "text": "Pivot" if mechanism == "lever" else "Load pivot", "color": C_PIVOT_TXT},
            {"point": plates_vis, "text": "Plates", "color": C_LOAD_TXT},
            {"point": g_end, "text": "Mg", "color": C_LOAD_TXT, "prefer": (0.2, 1.0)},
            {"point": grip, "text": "Contact", "color": C_OUT_TXT},
            {"point": f_end, "text": "F", "color": C_OUT_TXT, "prefer": (fx, fy)},
        ])
        if mechanism == "belt_cam":
            labels.append({"point": axis, "text": "Cam pivot", "color": C_PIVOT_TXT})

    # Optional anatomical segments (clean emerald dash-dot, no cluttered purple bar over the limb)
    if all(k in pose for k in ("joint", "proximal", "distal")):
        j, pr, di = pose["joint"], pose["proximal"], pose["distal"]
        ax.plot([pr[0], j[0], di[0]], [pr[1], j[1], di[1]],
                color=C_ANAT, lw=2.5, ls="-.", alpha=0.92, zorder=5, path_effects=HALO_THIN)
        ax.scatter([j[0], pr[0], di[0]], [j[1], pr[1], di[1]],
                   color=C_ANAT, edgecolor="white", linewidth=1.4, s=50, zorder=8)
        segments.extend([(pr, j), (j, di)])
        dots.extend([j, pr, di])
        labels.append({"point": j, "text": "Joint", "color": C_ANAT_TXT})

    # Draw scale bar only if it is physically distinct from the anatomical forearm segment
    scale_badge = None
    if all(k in pose for k in ("scale_start", "scale_end")):
        s0, s1 = pose["scale_start"], pose["scale_end"]
        sm = pose.get("scale_m")
        if sm:
            scale_badge = f"Scale ref: {sm:.2f} m"
        coincides_with_limb = (
            "joint" in pose and "distal" in pose
            and (
                (dist(s0, pose["joint"]) < 12 and dist(s1, pose["distal"]) < 12)
                or (dist(s1, pose["joint"]) < 12 and dist(s0, pose["distal"]) < 12)
            )
        )
        if not coincides_with_limb:
            ax.plot([s0[0], s1[0]], [s0[1], s1[1]],
                    color=C_SCALE, lw=2.2, ls=":", alpha=0.9, zorder=5.5, path_effects=HALO_THIN)
            ax.scatter([s0[0], s1[0]], [s0[1], s1[1]],
                       color=C_SCALE, edgecolor="white", linewidth=1.1, s=34, zorder=7)
            segments.append((s0, s1))

    # Top-left HUD badge & optional bottom-right scale badge (reserved as obstacle boxes!)
    hud_boxes = []
    parts = []
    if pose_index is not None:
        parts.append(f"Pose {pose_index}")
    if pose_meta:
        if "travel_pct" in pose_meta:
            pct = 0.0 if abs(pose_meta["travel_pct"]) < 0.05 else pose_meta["travel_pct"]
            parts.append(f"{pct:.0f}% travel")
        if "force_ratio" in pose_meta:
            parts.append(f"{pose_meta['force_ratio']:.2f} kgf/kg")
        if "angle_deg" in pose_meta:
            parts.append(f"Joint {pose_meta['angle_deg']:.0f}°")
    if parts:
        hud_text = "  ·  ".join(parts)
        ax.text(
            x0 + vw * 0.022, y0 + vh * 0.028, hud_text,
            fontsize=9.5, fontweight="bold", color="#f8fafc",
            va="top", ha="left", zorder=12,
            bbox={"facecolor": "#0f172a", "alpha": 0.86, "edgecolor": "#334155",
                  "linewidth": 1.0, "boxstyle": "round,pad=0.38"},
        )
        hud_w = min(vw * 0.78, len(hud_text) * vw * 0.012 + vw * 0.05)
        hud_boxes.append((x0, y0, x0 + hud_w + vw * 0.03, y0 + vh * 0.11))

    if scale_badge:
        ax.text(
            x1 - vw * 0.022, y1 - vh * 0.028, scale_badge,
            fontsize=8.2, fontweight="bold", color="#f5f3ff",
            va="bottom", ha="right", zorder=12,
            bbox={"facecolor": "#4c1d95", "alpha": 0.85, "edgecolor": C_SCALE,
                  "linewidth": 1.0, "boxstyle": "round,pad=0.3"},
        )
        sb_w = len(scale_badge) * vw * 0.011 + vw * 0.05
        hud_boxes.append((x1 - sb_w - vw * 0.03, y1 - vh * 0.095, x1, y1))

    _place_labels(ax, labels, segments, dots, (x0, x1, y0, y1), hud_boxes)

    ax.set(xlim=(x0, x1), ylim=(y1, y0))
    ax.axis("off")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() in (".jpg", ".jpeg"):
        tmp = out_path.with_suffix(".tmp.png")
        fig.savefig(tmp, dpi=125)
        with Image.open(tmp) as img:
            img.convert("RGB").save(out_path, format="JPEG", quality=jpeg_quality, optimize=True)
        tmp.unlink(missing_ok=True)
    else:
        fig.savefig(out_path, dpi=125)


def draw_report(result, observation, views, folder):
    samples = result["samples"]
    scaled = result["plate_kg"] is not None
    field = "force_kgf" if scaled else "newtons_per_kg"
    fig = Figure(figsize=(7, 4), layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    curve = result.get("resistance_curve")
    if curve:
        xs = [i for i in range(101)]
        scale = result["plate_kg"] if scaled else 9.80665
        ys = [evaluate_curve(curve, i / 100) * scale for i in xs]
        ax.plot(xs, ys, color="#0b7a75", linewidth=2.5)
        ax.fill_between(xs, ys, color="#0b7a75", alpha=0.12)
    if result["mechanism"] == "belt_cam":
        ax.scatter([s["travel_pct"] for s in samples], [s[field] for s in samples],
                   color="#0b7a75", edgecolor="white", linewidth=1.4, s=42, zorder=5)
    elif not curve:
        ax.plot([s["travel_pct"] for s in samples], [s[field] for s in samples],
                color="#0b7a75", linewidth=2.5)
    ax.set(xlim=(-3, 103), xlabel="Travel from first to last pose (%)",
           ylabel="Contact force (kgf)" if scaled else "Contact force per kg of plates (N/kg)",
           title="Resistance from added plates")
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=.25)
    fig.savefig(folder / "profile.png", dpi=150)

    poses_meta = result.get("poses", [])
    for i, (pose, path) in enumerate(zip(observation["poses"], views), 1):
        meta = poses_meta[i - 1] if i - 1 < len(poses_meta) else None
        draw_force_diagram(
            pose, result["mechanism"], path, folder / f"landmarks-{i:03}.png",
            pose_index=i, pose_meta=meta,
        )
