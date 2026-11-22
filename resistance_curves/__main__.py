import argparse
import re
import json
from pathlib import Path

from .mechanics import estimate
from .report import draw_report
from .vision import prepare


def run_estimate(observation, views, plate_kg, folder):
    result = estimate(observation, plate_kg)
    if views and len(views) != len(result["poses"]):
        raise ValueError("The number of observations must equal the number of prepared photos.")
    folder.mkdir(parents=True, exist_ok=False)
    draw_report(result, observation, views, folder)
    (folder / "profile.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print(result["evidence"])
    for label, sample in zip(("Start", "Finish"), (result["samples"][0], result["samples"][-1])):
        if plate_kg is None:
            print(f"{label}  {sample['newtons_per_kg']:.2f} N per kg of plates")
        else:
            print(f"{label}  {sample['force_kgf']:.2f} kgf ({sample['force_N']:.1f} N)")
    print(f"Profile saved in {folder}")


def main():
    parser = argparse.ArgumentParser(description="Estimate plate-induced contact force from side-view landmarks.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "estimate"):
        sub = commands.add_parser(name)
        sub.add_argument("--out", required=True, type=Path, help="New output directory")
        if name != "prepare":
            sub.add_argument("--plate-kg", type=float, help="Added plate mass on the modeled moving assembly")
        if name == "estimate":
            sub.add_argument("observation", type=Path)
        else:
            sub.add_argument("photos", type=Path, nargs="+")
    record = commands.add_parser("record", help="Validate and save a reviewed machine to the Git catalog")
    record.add_argument("observation", type=Path)
    record.add_argument("--slug", required=True)
    record.add_argument("--name", required=True)
    record.add_argument("--manufacturer", required=True)
    record.add_argument("--movement", required=True, help="e.g. elbow-flexion or compound")
    record.add_argument("--plate-kg", required=True, type=float)
    record.add_argument("--source", required=True)
    record.add_argument("--catalog", default=Path("catalog/machines"), type=Path)
    args = parser.parse_args()
    try:
        if args.command == "record":
            from .catalog import machine_view

            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug):
                raise ValueError("Use a lowercase hyphenated slug.")
            data = dict(name=args.name, manufacturer=args.manufacturer, movement=args.movement,
                        kind="Photo estimate", plate_kg=args.plate_kg, source=args.source,
                        observation=json.loads(args.observation.read_text()))
            machine_view(data)
            path = args.catalog / f"{args.slug}.json"
            serialized = json.dumps(data, indent=2, allow_nan=False) + "\n"
            with path.open("x") as file:
                file.write(serialized)
            print(path)
            return
        if args.command == "estimate":
            views = sorted(args.observation.parent.glob("pose-[0-9][0-9][0-9].jpg"))
            run_estimate(json.loads(args.observation.read_text()), views, args.plate_kg, args.out)
            return
        prepare(args.photos, args.out)
        print(f"Inspect the numbered images and follow {args.out}/prompt.txt.")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
