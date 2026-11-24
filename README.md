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

## GitHub Pages

Select **GitHub Actions** as the source under **Settings → Pages**. Pushes to `main` build and publish the catalog. To redeploy the current revision, run **Publish Resistance Atlas** from the Actions tab. The workflow reads the site URL from Pages, including any custom domain configured there.

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

## Manufacturer 3D models

Install `python -m pip install '.[models]'` for GLB, glTF 2.0, OBJ and STL, or `python -m pip install '.[step]'` to also read STEP/STP assemblies. Supply the model downloaded from the manufacturer or a local export from its CAD viewer. Keep glTF sidecar buffers alongside the main file. Keep licensed assets in the ignored work directory.

```sh
python -m resistance_curves prepare-model work/leg-press.step --up z --right y --source 'Manufacturer product URL' --out work/cad
python -m resistance_curves model-observation work/cad/model.json work/landmarks.json --out work/cad/observation.json
python -m resistance_curves estimate work/cad/observation.json --plate-kg 20 --out work/cad-review
```

Use the existing `record` command on that observation to add a **3D model estimate**. The generated record preserves the source, asset and geometry hashes, coordinate frame, landmark selections, and projected points. The static site builds without the optional import dependencies. A redistributable side-view image can be included at `site/static/model-views/<machine-slug>.jpg`.

The preparer makes three clean orthographic views per pose, all at one scale. The side image is `pose-001.jpg`; `end-001.jpg` and `top-001.jpg` help identify obscured parts. The manifest lists each mesh instance's transformed metric bounds and local-to-world matrix. Verify the bounds against published dimensions. Imported STEP and glTF geometry use metres; provide `--units mm`, `cm`, `m` or `in` for unitless OBJ/STL. Select the actual vertical and side-view horizontal axes, for example `--right=-x --up=z`.

For the included Innerscene leg press, the agent's landmark file can be written as:

```json
{
  "mechanism": "sled",
  "evidence": "End-face centers of the inclined press rail, Z up; the footplate and plates move together.",
  "poses": [{"rail_low": [-0.44, -0.45, 0.45], "rail_high": [-0.44, 0.76, 1.48]}]
}
```

These points are in metres in the imported world frame. A landmark can instead identify a mesh node and a point in native mesh-local coordinates, e.g. `{"node":"rail","local":[0,0,0]}`. If only image landmarks can be identified, set `"space":"side_pixels"` and use the 1000-pixel side images and the same landmark names as the photo workflow.

A straight sled requires one pose. With metric points the solver uses vertical rise divided by full 3D rail length. For a single rigid lever, supply `pivot`, `plates`, `grip`, and a signed `sweep_deg` at the top level with its justification in `evidence`. The model pose is the start of the lift and positive sweep is clockwise in the side view. For multiple poses, give `prepare-model` one mesh file per pose in movement order with consistent gravity and camera axes. A belt cam requires at least two distinct poses and the belt landmarks in each. The importer reads static triangle geometry and node transforms; export animation keyframes or CAD configurations as separate files. Meshes alone do not establish masses, counterweights, kinematic constraints or hidden cam profiles.

The sample leg press is an unbranded layout model. The catalog contains its derived curve and a side render under its public-domain license. [Original model and STEP download](https://www.innerscene.com/tools/library/3d-parts/leg-press-gym-equipment-75e948fb)

## Resistance functions

Every new machine record and estimate includes a `resistance_curve` object. Its input `t` is lifting travel divided by 100%, from bottom (0) to top (1) for a bottom-to-top lift. Its output is contact force in kgf per kilogram of plates. Multiply by plate mass for kgf, then by 9.80665 for newtons. Evaluate only inside the fitted stroke.

The fitter tries an endpoint-preserving polynomial of degree 0 through 3 in order of increasing complexity. At every reference sample, the absolute error must be at most 1% of the peak sampled resistance. It also checks interior extrema for negative resistance and overshoot beyond neighboring sample values by more than that tolerance. If those checks fail, it uses a shape-preserving piecewise cubic Hermite interpolator (PCHIP) through the samples. The tolerance describes approximation of the input data. Photo error and uncertainty between sparse observations are separate.

Polynomial coefficients are ordered constant first. For a spline, interval `i` has its own coefficient array in powers of `t - knots[i]`. The record includes the domain, units, sample count and maximum residual at the reference positions. A rigid lever’s samples come from its geometry model. A cam’s samples come from photographed positions. Two endpoints yield at most a line, with no independent evidence about the middle.

```python
import json
from pathlib import Path
from resistance_curves import evaluate_curve

machine = json.loads(Path("catalog/machines/hammer-strength-preacher-curl.json").read_text())
midpoint_kgf = machine["plate_kg"] * evaluate_curve(machine["resistance_curve"], 0.5)
```

Use `python -m resistance_curves fit catalog/machines/MACHINE-ID.json` to inspect a fit. Add `--write` to refresh it after editing source data. Hugo builds also derive fits for older records and flag stale stored coefficients.

## Custom plates and unloaded resistance

On a machine page enter total added kilograms or list individual plates on one moving assembly (for example, `20, 10, 2.5`). Zero plates shows the unloaded handle force. Both the resistance chart and predicted strength limit use the selected load. Strength comparisons apply limb share to the combined force.

The optional machine record field `base_resistance` holds `starting_kgf`, a `source` and optionally `url` and `finish_kgf`. One value assumes constant unloaded force. A different finish value gives a linear estimate between the two. The site starts unknown machines at zero and allows either endpoint to be edited. Hammer Strength specifies approximately 2 kg starting resistance per workarm for the PL-BI. Its change across travel is unknown. [Manufacturer specifications](https://shop.lifefitness.com/products/hammer-strength-plate-loaded-seated-biceps)

For a plate-only reference force R, total force at each position is B + R × L/Lref, with unloaded handle force B and custom plate mass L. For a reported force that already includes B, use B + (R − B) × L/Lref. Reported records may set the boolean `reference_includes_base`. The default for records without this field preserves the reference values by assuming the base was included. The Git record and its fitted coefficients always describe the original reference.

## Comparing resistance and strength

For a single-joint movement, the site compares external joint torque to an angle-specific capacity in N·m. It multiplies contact force in newtons by the limb’s share of the load and the perpendicular joint-to-force-line distance in metres. A scaled side view determines this arm for tangential rotary contact. Joint flexion is zero at full extension. Without calibrated anatomy the controls expose an assumed angle range and constant arm. The reported preacher curl has this limitation.

Add measurements as ordered `[flexion_degrees, torque_Nm]` pairs in a strength record with matching `movement`, `name`, and `source`. A lifter can also enter personal readings directly in the browser. Use the same joint action, posture, grip, and unilateral or bilateral basis. The study profile uses group-mean maximum elbow-flexion torque at 56°, 70° and 84°. The other included profile is explicitly synthetic. [Yang et al., Table 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC4135202/)

The first position at which demand reaches available capacity estimates a quasi-static limit for the selected load and strength settings. Highest demand divided by capacity identifies the likeliest sticking position under proportional strength loss. Available strength (%) is a scenario input. The model does not forecast fatigue over repetitions. It compares only overlapping angles. For sparse reports and cam poses it evaluates recorded positions by default. Enabling the fitted resistance function estimates demand between poses. For the crossing calculation the browser samples this function, includes the anatomical and strength knots, and linearly locates the crossing between adjacent compared positions. A crossing already exceeded at the beginning of the covered interval is reported as reached by that position. Compound movements have a force view only.

## Reading the result

Plate mass is in kg. Contact force is a magnitude in N and kgf (1 kgf = 9.80665 N). Omit the mass for N per kg of added plates. Supply the mass carried by the modeled assembly. For independent arms use the plates on one arm. A shared bar yields total contact force across both hands. Each pose uses its own pixel scale, which cancels in the force ratios.

| Mechanism | Calculation | Positions reported |
| --- | --- | --- |
| Rigid lever | Plate weight times horizontal pivot-to-plate offset divided by pivot-to-contact radius | Continuous model over the photographed grip-angle sweep |
| Two fixed axles with a single belt span | Balance gravity torque at the loading axle to find belt tension. Multiply tension by the perpendicular distance from the output axle to the belt line and divide by grip radius. | Observed grip angles only. Each pose has its own belt tangent. |
| Straight sled | Plate weight times the vertical rise per unit travel along the rail | Constant along the rail |

Rotary results describe force tangent to the grip path. Sled results describe force along the rail. Zero and 100% refer to the first and last photos. The solver assumes quasi-static balance, a level side projection and ideal bearings and belt. Machine self-weight, counterweights, friction and acceleration require additional measurements. Anatomical joint torque also requires the user's joint positions and force direction.

Pixel landmarks are estimates. Small changes to a short perpendicular moment arm can greatly change the result. Compare overlays with the original photos and rerun with plausible alternative points to see how much the result moves. Geometry checks reject evidently inconsistent rigid arms, reversed sequences within a sweep and impossible negative belt tension. They cannot validate hidden mechanisms or compensate for a tilted camera.

## Hammer Strength Seated Biceps (PL-BI)

The catalog models the Hammer Strength Plate-Loaded Seated Biceps (PL-BI) directly from side-view frames of the manufacturer's demonstration video, tracing the load arm, belt span, cam pivot, and grip across the stroke. [Original footage](https://www.youtube.com/watch?v=B27-cHMnlPE&t=17s)

An independent metric reference example is in `examples/hammer-strength-preacher-reference.json` for cross-checking against photo runs. Check that added load, contact point, side, and treatment of the unloaded mechanism match before comparing.

## Life Fitness Signature Series Biceps Curl

For the SPLBC, the camera shows the grips and moving plates through one repetition. The catalog contains the source frame identifiers, registration and pixel coordinates for both hands and the plate center. The ratio of plate rise to midpoint-of-grips path length gives 0.679 kgf per added kg over the filmed stroke. A check based on the orientation of the floor rails gives about 0.70. Perspective and the uncertain relative depth of the hands and plates limit the accuracy of both estimates. [Manufacturer demonstration](https://www.youtube.com/watch?v=fuMn3ukena4&t=52s)

The `motion_observation` input yields one interval mean for each pair of successive poses. Its `interval_mean` curve stores travel knots and a constant polynomial per interval. Each horizontal segment represents a travel-weighted average. Exact endpoint forces and a failure angle would require finer measurements. The website lets readers vary plates and unloaded force.

At 31.75 kg of plates, the SPLBC averages about 26.6 kgf in projection, or 27.2 kgf with the approximate camera correction. The Hammer PL-BI averages 27.2 kgf using its filmed hand path or 26.3 kgf if its two reported plate-only endpoints are joined linearly. These are combined handle forces with the specified starting resistances held constant. These whole-stroke averages cannot establish how hard the two machines feel at a particular elbow angle. [Life Fitness SPLBC specifications](https://www.lifefitness.com.au/commercial/signature-series-bicep-curl-splbc) · [Hammer Strength PL-BI specifications](https://shop.lifefitness.com/products/hammer-strength-plate-loaded-seated-biceps)

At 40 kg of plates, the first 26% of filmed hand travel gives about 26 kgf for the SPLBC. Over the same fraction of its own filmed travel, the Hammer gives about 34 kgf. To reproduce that comparison, register the Hammer plate and hand coordinates against its bearing, accumulate hand-path distance, interpolate plate height linearly at 25.918% of that distance and divide plate rise by distance traveled. Using the linear fit to the reported Hammer endpoints instead gives about 31 kgf averaged over the first 26%. The estimates use the catalog's constant unloaded forces. Both support a larger difference early in the lift than the stroke averages suggest. The first SPLBC interval spans only 22 enlarged pixels of registered rise (about 7 original pixels). The two videos also span different, uncalibrated elbow angles. The estimated gap is sensitive to landmark placement and cannot establish a personal load conversion.

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
