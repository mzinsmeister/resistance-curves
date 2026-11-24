"""Static force plots and annotated force-diagram overlays on the images the model saw."""

from math import atan2, degrees, dist, hypot
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, Polygon
from PIL import Image

from .anatomy import LANDMARKS
from .curves import evaluate_curve
from .mechanics import FIELDS


# High-contrast, colorblind-friendly engineering palette for force diagrams.
C_LOAD = "#0ea5e9"     # Cyan-blue: load arm, plates, gravity
C_OUT = "#f59e0b"      # Amber-orange: output/grip arm, tangential hand force
C_BELT = "#ec4899"     # Magenta: taut belt span & belt moment arms
C_PIVOT = "#ef4444"    # Crimson: fixed axles / pivots
C_ANAT = "#10b981"     # Emerald: anatomical joint & limb segments
C_SCALE = "#a855f7"    # Violet: metric reference scale bar


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


def _arrow(ax, start, end, color, lw=2.6, ms=15, zorder=6):
    patch = FancyArrowPatch(
        start, end,
        arrowstyle=f"-|>,head_length={ms * 0.55},head_width={ms * 0.35}",
        color=color, linewidth=lw, zorder=zorder, mutation_scale=1.0,
    )
    ax.add_patch(patch)


def _label(ax, point, text, color="#111827", offset=(8, -10), bg="#ffffff"):
    ax.annotate(
        text, point, xytext=offset, textcoords="offset points",
        fontsize=8.5, fontweight="bold", color=color, zorder=10,
        bbox={"facecolor": bg, "alpha": 0.88, "edgecolor": color,
              "linewidth": 0.9, "boxstyle": "round,pad=0.25"},
    )


def draw_force_diagram(pose, mechanism, view_path, out_path, *,
                       pose_index=None, pose_meta=None, jpeg_quality=88):
    """Render an annotated free-body / force diagram over a 1000x1000 prepared pose image."""
    fig = Figure(figsize=(7.2, 7.2), dpi=125)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])

    if view_path is not None and Path(view_path).is_file():
        with Image.open(view_path) as photo:
            ax.imshow(photo.convert("RGB"), extent=(0, 1000, 1000, 0))
    else:
        ax.set_facecolor("#f3f6f5")
        for g in range(100, 1000, 100):
            ax.axhline(g, color="#dce4e1", lw=0.7, zorder=0)
            ax.axvline(g, color="#dce4e1", lw=0.7, zorder=0)

    if mechanism == "sled":
        low, high = pose["rail_low"], pose["rail_high"]
        # Right-triangle decomposition: run + rise
        corner = (high[0], low[1])
        ax.plot([low[0], corner[0]], [low[1], corner[1]],
                color=C_LOAD, ls="--", lw=1.8, alpha=0.85, zorder=3)
        ax.plot([corner[0], high[0]], [corner[1], high[1]],
                color=C_LOAD, ls="--", lw=1.8, alpha=0.85, zorder=3)
        # Rail line & lifting direction arrow
        _arrow(ax, low, high, C_OUT, lw=3.2, ms=18, zorder=5)
        mid = ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2)
        # Gravity arrow downward from midpoint
        g_end = (mid[0], min(970, mid[1] + 135))
        _arrow(ax, mid, g_end, C_LOAD, lw=2.8, ms=16, zorder=6)
        _label(ax, g_end, "Mg (gravity)", C_LOAD, offset=(8, -4))
        # Component along rail
        ux, uy = _unit(high[0] - low[0], high[1] - low[1])
        f_end = (mid[0] + ux * 135, mid[1] + uy * 135)
        _arrow(ax, mid, f_end, C_OUT, lw=3.0, ms=16, zorder=7)
        _label(ax, f_end, "F = Mg sin θ", C_OUT, offset=(8, -14))
        ax.scatter([low[0], high[0]], [low[1], high[1]],
                   color=C_PIVOT, edgecolor="white", linewidth=1.6, s=70, zorder=8)
        _label(ax, low, "Rail low", C_PIVOT, offset=(8, 10))
        _label(ax, high, "Rail high", C_PIVOT, offset=(-70, -14))
        rise = low[1] - high[1]
        run = abs(high[0] - low[0])
        ang = degrees(atan2(rise, run)) if run or rise else 0.0
        _label(ax, (corner[0], (low[1] + high[1]) / 2), f"θ = {ang:.1f}°", C_LOAD, offset=(8, 0))

    elif mechanism in ("lever", "belt_cam"):
        pivot = pose["pivot"]
        plates = pose["plates"]
        grip = pose["grip"]
        axis = pose.get("cam_pivot", pivot)

        # Horizontal gravity moment arm from pivot to plate plumb line
        plumb_pt = (plates[0], pivot[1])
        ax.plot([pivot[0], plumb_pt[0]], [pivot[1], plumb_pt[1]],
                color=C_LOAD, ls="--", lw=2.0, alpha=0.9, zorder=3)
        ax.plot([plates[0], plumb_pt[0]], [plates[1], plumb_pt[1]],
                color=C_LOAD, ls=":", lw=1.6, alpha=0.75, zorder=3)
        # Load lever arm
        ax.plot([pivot[0], plates[0]], [pivot[1], plates[1]],
                color=C_LOAD, lw=3.0, zorder=4)
        # Gravity arrow downward at plates
        g_len = min(130, max(75, 960 - plates[1]))
        g_end = (plates[0], min(975, plates[1] + g_len))
        _arrow(ax, plates, g_end, C_LOAD, lw=2.8, ms=16, zorder=6)
        _label(ax, g_end, "Mg", C_LOAD, offset=(8, -4))

        # Output arm (axis -> grip)
        ax.plot([axis[0], grip[0]], [axis[1], grip[1]],
                color=C_OUT, lw=3.0, zorder=4)
        # Tangential handle force arrow perpendicular to output arm
        rx, ry = grip[0] - axis[0], grip[1] - axis[1]
        tx, ty = _unit(-ry, rx)
        # Point tangent in the upward/opposing half-plane for readability
        if ty > 0:
            tx, ty = -tx, -ty
        f_len = 110
        f_end = (max(25, min(975, grip[0] + tx * f_len)),
                 max(25, min(975, grip[1] + ty * f_len)))
        _arrow(ax, grip, f_end, C_OUT, lw=2.8, ms=16, zorder=6)
        _label(ax, f_end, "F_hand", C_OUT, offset=(6, -12))

        if mechanism == "belt_cam":
            bl, bc = pose["belt_load"], pose["belt_cam"]
            # Belt span line with tension arrow
            ax.plot([bl[0], bc[0]], [bl[1], bc[1]], color=C_BELT, lw=3.0, zorder=5)
            bmid = ((bl[0] + bc[0]) / 2, (bl[1] + bc[1]) / 2)
            bux, buy = _unit(bc[0] - bl[0], bc[1] - bl[1])
            _arrow(ax, (bmid[0] - bux * 35, bmid[1] - buy * 35),
                   (bmid[0] + bux * 35, bmid[1] + buy * 35), C_BELT, lw=3.0, ms=16, zorder=7)
            _label(ax, bmid, "Belt T", C_BELT, offset=(8, 0))
            # Perpendicular moment arms to belt line
            p_proj = _project_on_line(pivot, bl, bc)
            c_proj = _project_on_line(axis, bl, bc)
            ax.plot([pivot[0], p_proj[0]], [pivot[1], p_proj[1]],
                    color=C_BELT, ls="--", lw=1.8, alpha=0.9, zorder=4)
            ax.plot([axis[0], c_proj[0]], [axis[1], c_proj[1]],
                    color=C_BELT, ls="--", lw=1.8, alpha=0.9, zorder=4)
            ax.scatter([bl[0], bc[0]], [bl[1], bc[1]],
                       color=C_BELT, edgecolor="white", linewidth=1.4, s=55, zorder=8)

        # Landmarks & labels
        ax.scatter([pivot[0]], [pivot[1]], color=C_PIVOT, edgecolor="white", linewidth=1.8, s=85, zorder=9)
        _label(ax, pivot, "Pivot" if mechanism == "lever" else "Load pivot", C_PIVOT, offset=(10, 10))
        if mechanism == "belt_cam":
            ax.scatter([axis[0]], [axis[1]], color=C_PIVOT, edgecolor="white", linewidth=1.8, s=85, zorder=9)
            _label(ax, axis, "Cam pivot", C_PIVOT, offset=(10, -14))
        ax.scatter([plates[0]], [plates[1]], color=C_LOAD, edgecolor="white", linewidth=1.6, s=70, zorder=9)
        _label(ax, plates, "Plates", C_LOAD, offset=(10, -14))
        ax.scatter([grip[0]], [grip[1]], color=C_OUT, edgecolor="white", linewidth=1.6, s=70, zorder=9)
        _label(ax, grip, "Grip", C_OUT, offset=(10, 10))

    # Optional anatomical segments & scale reference
    if all(k in pose for k in ("joint", "proximal", "distal")):
        j, pr, di = pose["joint"], pose["proximal"], pose["distal"]
        ax.plot([pr[0], j[0], di[0]], [pr[1], j[1], di[1]],
                color=C_ANAT, lw=2.6, ls="-.", alpha=0.9, zorder=5)
        ax.scatter([j[0], pr[0], di[0]], [j[1], pr[1], di[1]],
                   color=C_ANAT, edgecolor="white", linewidth=1.3, s=52, zorder=8)
        _label(ax, j, "Joint", C_ANAT, offset=(-52, -14))
    if all(k in pose for k in ("scale_start", "scale_end")):
        s0, s1 = pose["scale_start"], pose["scale_end"]
        ax.plot([s0[0], s1[0]], [s0[1], s1[1]], color=C_SCALE, lw=2.4, zorder=6)
        ax.scatter([s0[0], s1[0]], [s0[1], s1[1]], color=C_SCALE, s=36, zorder=7)
        smid = ((s0[0] + s1[0]) / 2, (s0[1] + s1[1]) / 2)
        sm = pose.get("scale_m")
        _label(ax, smid, f"Scale {sm:.2f} m" if sm else "Scale", C_SCALE, offset=(6, 8))

    # Compact HUD badge in top-left corner
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
        ax.text(
            20, 24, "  ·  ".join(parts),
            fontsize=10, fontweight="bold", color="#f8fafc",
            va="top", ha="left", zorder=12,
            bbox={"facecolor": "#0f172a", "alpha": 0.84, "edgecolor": "#334155",
                  "linewidth": 1.0, "boxstyle": "round,pad=0.4"},
        )

    ax.set(xlim=(0, 1000), ylim=(1000, 0))
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
