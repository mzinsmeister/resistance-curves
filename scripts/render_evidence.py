#!/usr/bin/env python3
"""Render annotated force-diagram evidence images for every observation-based machine."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from resistance_curves.mechanics import estimate
from resistance_curves.report import draw_force_diagram


def find_pose_views(slug, pose_count):
    candidates = [
        ROOT / "work" / slug / "poses",
        ROOT / "work" / slug / "session",
        ROOT / "work" / slug,
    ]
    if slug == "innerscene-inclined-leg-press":
        candidates.insert(0, ROOT / "work/innerscene/session")
    elif slug == "hammer-strength-preacher-curl":
        candidates.insert(0, ROOT / "work/pl-bi-manufacturer")
    for folder in candidates:
        if not folder.is_dir():
            continue
        imgs = sorted(folder.glob("pose-*.jpg")) + sorted(folder.glob("pose-*.png"))
        imgs = sorted(set(imgs))
        if len(imgs) == pose_count:
            return imgs
    model_view = ROOT / "site/static/model-views" / f"{slug}.jpg"
    if pose_count == 1 and model_view.is_file():
        return [model_view]
    return [None] * pose_count


def render_all(force=False):
    for path in sorted((ROOT / "catalog/machines").glob("*.json")):
        slug = path.stem
        record = json.loads(path.read_text())
        if "observation" not in record:
            continue
        obs = record["observation"]
        poses = obs.get("poses", [])
        if not poses:
            continue
        out_dir = ROOT / "site/static/evidence" / slug
        views = find_pose_views(slug, len(poses))
        # Skip if existing evidence images are present and we have no local photo views to re-render
        existing = sorted(out_dir.glob("pose-*.jpg")) if out_dir.is_dir() else []
        if not force and len(existing) == len(poses) and all(v is None for v in views):
            continue
        result = estimate(obs, record["plate_kg"])
        # Clean stale files in out_dir before writing
        if out_dir.is_dir():
            for old in out_dir.glob("pose-*.*"):
                old.unlink()
        for idx, (pose, view, meta) in enumerate(zip(poses, views, result["poses"]), 1):
            draw_force_diagram(
                pose,
                result["mechanism"],
                view,
                out_dir / f"pose-{idx:03}.jpg",
                pose_index=idx,
                pose_meta=meta,
                jpeg_quality=88,
            )
        src_note = "photos" if any(v is not None for v in views) else "schematic"
        print(f"Rendered {len(poses)} force diagram(s) for {slug} ({src_note})")


if __name__ == "__main__":
    render_all(force="--force" in sys.argv)
