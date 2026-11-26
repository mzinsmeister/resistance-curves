#!/usr/bin/env python3
"""Render the Git catalog using Hugo. No database service or model credentials required."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resistance_curves.curves import evaluate_curve
from resistance_curves.catalog import check_pairs, machine_view
from resistance_curves.mechanics import estimate as estimate_mechanics

DEFAULT_LOAD_KG = 20.0


def read_records(folder):
    for path in sorted(folder.glob("*.json")):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", path.stem):
            raise ValueError(f"Use a lowercase hyphenated slug for {path.name}")
        yield path, json.loads(path.read_text())


def classify_shape(ratios):
    r_min, r_max = min(ratios), max(ratios)
    if r_max - r_min <= 0.04 * max(r_max, 1e-6):
        return "Constant"
    peak_i = ratios.index(r_max)
    min_i = ratios.index(r_min)
    start_r, end_r = ratios[0], ratios[-1]
    if peak_i >= 80 and end_r > start_r * 1.05:
        return "Ascending"
    if peak_i <= 20 and start_r > end_r * 1.05:
        return "Descending"
    if r_max > max(start_r, end_r) * 1.04:
        return "Bell curve"
    if r_min < min(start_r, end_r) * 0.96:
        return "U-shaped"
    return "Ascending" if end_r >= start_r else "Descending"


def is_example_record(raw, data=None):
    """Identify synthetic, unbranded CAD-library, or explicitly flagged example records."""
    if raw.get("example") is True:
        return True
    src = data or raw
    kind = str(src.get("kind", "")).lower()
    meta = f"{src.get('manufacturer', '')} {kind} {src.get('source', '')}".lower()
    return (
        kind.startswith("synthetic")
        or any(tok in meta for tok in ("example", "cad library", "layout model", "unbranded"))
    )


def spark_geometry(points):
    top = max(max(y for _, y in points), 1e-6)
    coords = [(x, 92.0 - 80.0 * y / top) for x, y in points]
    line = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
    area = f"0,96 {line} 100,96"
    peak_idx = max(range(len(points)), key=lambda i: points[i][1])
    peak_xy = [round(coords[peak_idx][0], 2), round(coords[peak_idx][1], 2)]
    return line, area, peak_xy


def discover_evidence(slug, raw):
    folder = ROOT / "site/static/evidence" / slug
    if not folder.is_dir():
        return []
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    )
    if not files:
        return []
    pose_travel = []
    if "observation" in raw:
        try:
            prof = estimate_mechanics(raw["observation"], raw["plate_kg"])
            pose_travel = [p.get("travel_pct") for p in prof.get("poses", [])]
        except Exception:
            pose_travel = []
    images = []
    n = len(files)
    for idx, img in enumerate(files):
        pct = pose_travel[idx] if idx < len(pose_travel) and pose_travel[idx] is not None else None
        if pct is not None and abs(pct) < 0.05:
            pct = 0.0
        if n == 1:
            label = "Force diagram"
        elif idx == 0:
            label = f"Start ({pct:.0f}%)" if pct is not None else "Start (0%)"
        elif idx == n - 1:
            label = f"Finish ({pct:.0f}%)" if pct is not None else "Finish (100%)"
        else:
            label = f"Pose {idx + 1} ({pct:.0f}%)" if pct is not None else f"Pose {idx + 1}"
        images.append({"src": f"evidence/{slug}/{img.name}", "label": label})
    return images


def build(out):
    marker = out / ".resistance-atlas-output"
    if out.exists() and any(out.iterdir()) and not marker.is_file():
        raise ValueError(f"Choose an empty output directory or a previous Atlas build: {out}")
    with tempfile.TemporaryDirectory(prefix="resistance-hugo-") as temporary:
        stage = Path(temporary)
        for item in ("layouts", "static"):
            shutil.copytree(ROOT / "site" / item, stage / item)
        shutil.copy(ROOT / "site/hugo.toml", stage)
        content = stage / "content/machines"
        content.mkdir(parents=True)
        downloads = stage / "static/records"
        downloads.mkdir()

        strength = []
        for path, record in read_records(ROOT / "catalog/strength"):
            check_pairs(record["points"], 0.000001, 180)
            if not all(record.get(k) for k in ("name", "movement", "source")):
                raise ValueError(f"Incomplete strength profile {path.name}")
            strength.append(record)

        for path, raw in read_records(ROOT / "catalog/machines"):
            try:
                data = machine_view(raw)
            except ValueError as exc:
                raise ValueError(f"{path.name}: {exc}") from exc

            def strength_rank(s):
                nm = s["name"].lower()
                is_pooled = "average adult" in nm and "male" not in nm and "female" not in nm and "women" not in nm and "men" not in nm
                span = s["points"][-1][0] - s["points"][0][0]
                return (0 if is_pooled else 1, -span, nm)

            data["strength"] = sorted(
                [s for s in strength if s["movement"] == data["movement"]],
                key=strength_rank,
            )
            curve = data["resistance_curve"]
            if curve["type"] == "polynomial":
                terms = []
                for power, coefficient in enumerate(curve["coefficients"]):
                    sign = " − " if coefficient < 0 else (" + " if power else "")
                    terms.append(f"{sign}{abs(coefficient):.6g}{('', 't', 't²', 't³')[power]}")
                data["formula"] = "".join(terms)

            base = data.get("base_resistance", {})
            start_base = base.get("starting_kgf", 0.0)
            finish_base = base.get("finish_kgf", start_base)
            ref_includes = data.get("reference_includes_base", False)

            ratios = []
            default_trace = []
            for i in range(101):
                t = i / 100.0
                b_i = start_base + (finish_base - start_base) * t
                ref_force = evaluate_curve(curve, t) * data["plate_kg"]
                plate_contrib = max(0.0, ref_force - b_i) if ref_includes else max(0.0, ref_force)
                ratio = plate_contrib / data["plate_kg"]
                ratios.append(ratio)
                default_trace.append((float(i), b_i + ratio * DEFAULT_LOAD_KG))

            peak_val = max(y for _, y in default_trace)
            peak_pct = max(range(101), key=lambda i: default_trace[i][1])
            min_val = min(y for _, y in default_trace)
            mean_val = (
                sum(0.5 * (default_trace[i - 1][1] + default_trace[i][1]) for i in range(1, 101))
                / 100.0
            )

            line, area, peak_xy = spark_geometry(default_trace)
            data["trace"] = line
            data["area"] = area
            data["peak_xy"] = peak_xy
            data["curve_shape"] = classify_shape(ratios)
            data["default_load_kg"] = DEFAULT_LOAD_KG
            data["default_start_kgf"] = default_trace[0][1]
            data["default_finish_kgf"] = default_trace[-1][1]
            data["default_peak_kgf"] = peak_val
            data["default_peak_pct"] = peak_pct
            data["default_min_kgf"] = min_val
            data["default_mean_kgf"] = mean_val
            data["is_example"] = is_example_record(raw, data)
            src_low = (data["source"] + " " + raw.get("observation", {}).get("evidence", "")).lower()
            is_unilateral = any(
                k in src_low for k in (
                    "single-arm", "one arm", "one independent", "per-side", "per arm",
                    "independent arm", "one workarm", "iso-lateral", "unilateral",
                )
            ) and not any(k in src_low for k in ("both hands on one", "both legs on one", "shared workarm", "combined tangential", "combined contact"))
            data["default_share"] = 100 if is_unilateral else 50
            data["evidence_images"] = discover_evidence(path.stem, raw)

            if data["mechanism"] == "motion_intervals":
                knots = curve["knots"]
                bands = []
                for a, b, (ratio,) in zip(knots, knots[1:], curve["coefficients"]):
                    force = DEFAULT_LOAD_KG * ratio + start_base + (finish_base - start_base) * (a + b) / 2
                    bands.append([100 * a, 100 * b, force])
                data["bands"] = bands

            metadata = {"title": data["name"], "params": {"machine": data, "slugid": path.stem}}
            (content / f"{path.stem}.md").write_text(json.dumps(metadata, allow_nan=False) + "\n")
            (downloads / path.name).write_text(json.dumps(dict(raw, resistance_curve=curve), indent=2) + "\n")

        subprocess.run(
            [os.environ.get("HUGO", "hugo"), "--source", str(stage),
             "--destination", str(out.resolve()), "--cleanDestinationDir"],
            check=True,
        )
        marker.touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "site/public")
    build(parser.parse_args().out)
