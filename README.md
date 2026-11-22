# Resistance Atlas

A Git catalog of plate-loaded gym machines, rendered as a static website by **Hugo**. Each machine has one reviewable JSON file under `catalog/machines/`. Each strength profile has one under `catalog/strength/`. A coding agent handles image interpretation and landmark placement. The Python library handles geometry, units and force calculations.

## Build and browse

Use Python 3.10+, Node for the comparison tests, and Hugo 0.146 or newer. Run from the repository root:

```sh
python -m pip install .
python -m unittest discover -s tests
node --test tests/model.test.cjs
python scripts/build_site.py
python -m http.server 8080 --directory site/public
```

Open <http://localhost:8080/>. Deploy the contents of `site/public/` to any static host, including a subdirectory. Each machine page ships HTML, a reference chart, sample table and the source record. JavaScript adjusts load, overlays strength and estimates the limiting position entirely in the browser. The build uses a temporary Hugo content tree and checks all records. Set `HUGO` to an executable path if needed.

## Agent workflow

Give a vision-capable coding agent the photos, the loaded plate mass, the stroke order and any known dimensions. Ask it to follow [AGENTS.md](AGENTS.md) and add the machine to the catalog. Take level side views with the pivots, contact, plates and any belt span visible. A middle photo matters for cams. The agent prepares the images, marks landmarks, estimates scale, reviews overlays, records its evidence and rebuilds the site. All commands run locally.

```sh
python -m resistance_curves prepare bottom.jpg top.jpg --out work/poses
# The coding agent inspects the two prepared images and writes observation.json.
python -m resistance_curves estimate work/poses/observation.json --plate-kg 31.75 --out work/review
python -m resistance_curves record work/poses/observation.json --slug machine-id \
  --name 'Machine name' --manufacturer 'Manufacturer' --movement elbow-flexion \
  --plate-kg 31.75 --source 'Photo identifiers, setup and uncertainties'
python scripts/build_site.py
```

## Comparing resistance and strength

For a single-joint movement, the site compares external joint torque to an angle-specific capacity in N·m. It multiplies contact force in newtons by the limb’s share of the load and the perpendicular joint-to-force-line distance in metres. A scaled side view determines this arm for tangential rotary contact. Joint flexion is zero at full extension. Without calibrated anatomy the controls expose an assumed angle range and constant arm. The reported preacher curl has this limitation.

Add measurements as ordered `[flexion_degrees, torque_Nm]` pairs in a strength record with matching `movement`, `name`, and `source`. A lifter can also enter personal readings directly in the browser. Use the same joint action, posture, grip, and unilateral or bilateral basis. The study profile uses group-mean maximum elbow-flexion torque at 56°, 70° and 84°. The other included profile is explicitly synthetic. [Yang et al., Table 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC4135202/)

The first position at which demand reaches available capacity estimates a quasi-static limit for the selected load and strength settings. Highest demand divided by capacity identifies the likeliest sticking position under proportional strength loss. Available strength (%) is a scenario input. The model does not forecast fatigue over repetitions. It compares only overlapping angles. For sparse reports and cam poses it evaluates recorded positions by default. Opting into piecewise-linear interpolation estimates a crossing between poses. A crossing already exceeded at the beginning of the covered interval is reported as reached by that position. Compound movements have a force view only.

## Reading the result

Plate mass is in kg. Contact force is a magnitude in N and kgf (1 kgf = 9.80665 N). Omit the mass for N per kg of added plates. Supply the mass carried by the modeled assembly. For independent arms use the plates on one arm. A shared bar yields total contact force across both hands. Each pose uses its own pixel scale, which cancels in the force ratios.

| Mechanism | Calculation | Positions reported |
| --- | --- | --- |
| Rigid lever | Plate weight times horizontal pivot-to-plate offset divided by pivot-to-contact radius | Continuous model over the photographed grip-angle sweep |
| Two fixed axles with a single belt span | Balance gravity torque at the loading axle to find belt tension. Multiply tension by the perpendicular distance from the output axle to the belt line and divide by grip radius. | Observed grip angles only. Each pose has its own belt tangent. |
| Straight sled | Plate weight times the vertical rise per unit travel along the rail | Constant along the rail |

Rotary results describe force tangent to the grip path. Sled results describe force along the rail. Zero and 100% refer to the first and last photos. The solver assumes quasi-static balance, a level side projection and ideal bearings and belt. Machine self-weight, counterweights, friction and acceleration require additional measurements. Anatomical joint torque also requires the user's joint positions and force direction.

Pixel landmarks are estimates. Small changes to a short perpendicular moment arm can greatly change the result. Compare overlays with the original photos and rerun with plausible alternative points to see how much the result moves. Geometry checks reject evidently inconsistent rigid arms, reversed sequences within a sweep and impossible negative belt tension. They cannot validate hidden mechanisms or compensate for a tilted camera.

## Hammer Strength preacher curl reference

The figures supplied for the @juandsamudio analysis correspond to **31.75 kg of plates**, **22.68 kgf (222.4 N)** at the bottom and **25.85 kgf (253.5 N)** at the top. The top value is 14% higher. Those endpoints alone leave the middle of the curve undetermined. The screenshot's separate worked pose gives about 533.8 N belt tension, a 0.1016 m cam moment arm and an assumed 0.254 m effective hand arm, yielding about 213.5 N (21.77 kgf). The slide does not identify this as either quoted endpoint.

The converted reference is in `examples/hammer-strength-preacher-reference.json` for comparison with an independent photo run. Check that added load, contact point, side and treatment of the unloaded mechanism match before comparing.

## Library

```python
import json
from pathlib import Path
from resistance_curves import estimate

observation = json.loads(Path("examples/belt-cam.json").read_text())
profile = estimate(observation, plate_kg=20)
print(profile["samples"][0]["force_kgf"])
```

The package also exports `moment_arm(pivot, start, end)` and `tangential_force(tension, cam_arm, grip_radius)`. Landmark coordinates use the square 1000-pixel frame with y increasing downward. Angles increase clockwise. The signed load-side balance uses a belt directed from the loading lever toward the output cam. All lengths in a moment-arm ratio must use the same unit.
