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


def read_records(folder):
    for path in sorted(folder.glob("*.json")):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", path.stem):
            raise ValueError(f"Use a lowercase hyphenated slug for {path.name}")
        yield path, json.loads(path.read_text())


def chart(points):
    top = max(max(y for _, y in points), 1)
    return " ".join(f"{x:.3f},{96 - 88*y/top:.3f}" for x, y in points)


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
            data["strength"] = [s for s in strength if s["movement"] == data["movement"]]
            curve = data["resistance_curve"]
            if curve["type"] == "polynomial":
                terms = []
                for power, coefficient in enumerate(curve["coefficients"]):
                    sign = " − " if coefficient < 0 else (" + " if power else "")
                    terms.append(f"{sign}{abs(coefficient):.6g}{('', 't', 't²', 't³')[power]}")
                data["formula"] = "".join(terms)
            base = data.get("base_resistance", {})
            start = base.get("starting_kgf", 0)
            finish = base.get("finish_kgf", start)
            if data["mechanism"] == "motion_intervals":
                knots = curve["knots"]
                bands = []
                for a, b, (ratio,) in zip(knots, knots[1:], curve["coefficients"]):
                    force = data["plate_kg"] * ratio + start + (finish-start) * (a+b)/2
                    bands.append([100*a, 100*b, force])
                data["bands"] = bands
                data["default_mean_kgf"] = sum((b-a)*force/100 for a, b, force in bands)
                top = max(1, *(force for a, b, force in bands))
                data["segments"] = [[a, b, 96 - 88*force/top] for a, b, force in bands]
            else:
                trace = data["points"]
                if data["mechanism"] not in ("reported", "belt_cam"):
                    trace = [(i, evaluate_curve(curve, i / 100) * data["plate_kg"]) for i in range(101)]
                if not data.get("reference_includes_base", False):
                    trace = [(pct, force + start + (finish - start) * pct / 100) for pct, force in trace]
                data["default_start_kgf"] = trace[0][1]
                data["default_finish_kgf"] = trace[-1][1]
                data["trace"] = chart(trace)
                data["markers"] = [p.split(",") for p in data["trace"].split()] if data["mechanism"] in ("reported", "belt_cam") else []
            metadata = {"title": data["name"], "params": {"machine": data, "slugid": path.stem}}
            (content / f"{path.stem}.md").write_text(json.dumps(metadata, allow_nan=False) + "\n")
            # Older input records can omit the derived function. Export it for all consumers.
            (downloads / path.name).write_text(json.dumps(dict(raw, resistance_curve=curve), indent=2) + "\n")
        subprocess.run([os.environ.get("HUGO", "hugo"), "--source", str(stage),
                        "--destination", str(out.resolve()), "--cleanDestinationDir"], check=True)
        marker.touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "site/public")
    build(parser.parse_args().out)
