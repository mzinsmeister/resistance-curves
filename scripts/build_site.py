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
            data["trace"] = chart(data["points"])
            data["markers"] = [p.split(",") for p in data["trace"].split()] if len(data["points"]) <= 15 else []
            metadata = {"title": data["name"], "params": {"machine": data, "slugid": path.stem}}
            (content / f"{path.stem}.md").write_text(json.dumps(metadata, allow_nan=False) + "\n")
            shutil.copy(path, downloads)
        subprocess.run([os.environ.get("HUGO", "hugo"), "--source", str(stage),
                        "--destination", str(out.resolve()), "--cleanDestinationDir"], check=True)
        marker.touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "site/public")
    build(parser.parse_args().out)
