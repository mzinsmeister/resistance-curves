import json
from pathlib import Path
import unittest

from resistance_curves.catalog import check_pairs, machine_view

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_calibrated_tangent_and_angles(self):
        data = json.loads((ROOT / "catalog/machines/single-arm-lever-curl.json").read_text())
        v = machine_view(data)
        for (travel, angle, arm), expected in zip(v["geometry"], [20, 55, 90, 125]):
            self.assertAlmostEqual(angle, expected, places=2)
            self.assertAlmostEqual(arm, .30, places=4)
        del data["observation"]["poses"][0]["scale_source"]
        with self.assertRaisesRegex(ValueError, "scale_source"):
            machine_view(data)

    def test_all_catalog_machines_have_smooth_curves_and_no_social_refs(self):
        machines = sorted((ROOT / "catalog/machines").glob("*.json"))
        self.assertGreaterEqual(len(machines), 10)
        for path in machines:
            raw_text = path.read_text()
            self.assertNotIn("instagram", raw_text.lower(), f"Found instagram reference in {path.name}")
            self.assertNotIn("juandsamudio", raw_text.lower(), f"Found personal handle in {path.name}")
            record = json.loads(raw_text)
            view = machine_view(record)
            curve = view["resistance_curve"]
            self.assertIn(curve["type"], ("polynomial", "pchip"), f"{path.name} should have a smooth curve")

    def test_video_work_is_invariant_to_camera_translation(self):
        from resistance_curves.work_check import motion_work_check

        poses = [
            dict(anchor=[50, 60], plates=[10, 80], hand=[100, 30], handle_cap=[100, 30]),
            dict(anchor=[55, 70], plates=[15, 70], hand=[105, 15], handle_cap=[105, 10]),
        ]
        result = motion_work_check(poses)
        self.assertAlmostEqual(result["hand_kgf_per_kg"], 20/25)
        self.assertAlmostEqual(result["handle_cap_kgf_per_kg"], 20/30)

    def test_motion_intervals_preserve_total_work(self):
        from resistance_curves.curves import evaluate_curve

        record = {
            "name": "Interval work check test",
            "manufacturer": "Test",
            "movement": "elbow-flexion",
            "kind": "Video interval estimates",
            "plate_kg": 20.0,
            "source": "Unit test fixture for motion_intervals conservation of work.",
            "motion_observation": {
                "url": "https://example.invalid/demo",
                "uncertainty": "Fixture only.",
                "poses": [
                    {"anchor": [0, 0], "plates": [0, 100], "near_hand": [0, 0], "far_hand": [0, 0]},
                    {"anchor": [0, 0], "plates": [0, 80], "near_hand": [30, 0], "far_hand": [30, 0]},
                    {"anchor": [0, 0], "plates": [0, 40], "near_hand": [80, 0], "far_hand": [80, 0]},
                ],
            },
        }
        data = machine_view(record)
        curve = data["resistance_curve"]
        self.assertEqual(curve["type"], "interval_mean")
        mean = sum((b-a) * evaluate_curve(curve, (a+b)/2)
                   for a, b in zip(curve["knots"], curve["knots"][1:]))
        self.assertAlmostEqual(mean, 60/80)
        self.assertAlmostEqual(mean, data["motion_evidence"]["mean_kgf_per_kg"])
        record["motion_observation"]["poses"].reverse()
        with self.assertRaisesRegex(ValueError, "ascending"):
            machine_view(record)

    def test_catalog_starting_resistance_and_empirical_strength(self):
        record = json.loads((ROOT / "catalog/machines/hammer-strength-preacher-curl.json").read_text())
        self.assertEqual(machine_view(record)["base_resistance"]["starting_kgf"], 1.8)
        record["base_resistance"]["starting_kgf"] = -1
        with self.assertRaisesRegex(ValueError, "Base resistance"):
            machine_view(record)
        for sp in sorted((ROOT / "catalog/strength").glob("*.json")):
            s = json.loads(sp.read_text())
            self.assertNotIn("synthetic", s["source"].lower(), f"Synthetic strength profile {sp.name}")
            check_pairs(s["points"], 1e-6, 180)

    def test_belt_cam_kinematic_consistency_and_ui_strength_default(self):
        import math
        from resistance_curves.mechanics import estimate

        # Strength comparison must default to normalized shape comparison (% of peak) to avoid arbitrary Nm mismatch
        page_tpl = (ROOT / "site/layouts/page.html").read_text()
        self.assertIn('id="normalize-strength" type="checkbox" checked', page_tpl)

        # Every catalog belt_cam must agree with kinematic rotation ratio d(theta_load)/d(theta_cam)
        for path in sorted((ROOT / "catalog/machines").glob("*.json")):
            record = json.loads(path.read_text())
            obs = record.get("observation")
            if not obs or obs.get("mechanism") != "belt_cam":
                continue
            prof = estimate(obs, record["plate_kg"])
            poses = obs["poses"]
            th_load = [math.atan2(p["plates"][1] - p["pivot"][1], p["plates"][0] - p["pivot"][0]) for p in poses]
            th_cam = [math.atan2(p["grip"][1] - p["cam_pivot"][1], p["grip"][0] - p["cam_pivot"][0]) for p in poses]
            d_load = sum(abs(math.remainder(b - a, 2 * math.pi)) for a, b in zip(th_load, th_load[1:]))
            d_cam = sum(abs(math.remainder(b - a, 2 * math.pi)) for a, b in zip(th_cam, th_cam[1:]))
            kin_ratio = d_load / d_cam
            stat_ratio = sum(abs(m["cam_belt_arm_px"] / m["load_belt_arm_px"]) for m in prof["poses"]) / len(prof["poses"])
            self.assertLess(abs(kin_ratio - stat_ratio) / stat_ratio, 0.20,
                            f"{path.name}: kinematic ratio {kin_ratio:.3f} disagrees with static {stat_ratio:.3f}")

    def test_all_catalog_levers_have_consistent_individual_radii(self):
        import math

        for path in sorted((ROOT / "catalog/machines").glob("*.json")):
            record = json.loads(path.read_text())
            obs = record.get("observation")
            if not obs or obs.get("mechanism") != "lever":
                continue
            poses = obs.get("poses") or []
            if len(poses) < 2:
                continue
            rg = [math.dist(p["pivot"], p["grip"]) for p in poses]
            rp = [math.dist(p["pivot"], p["plates"]) for p in poses]
            self.assertLessEqual(max(rg) / min(rg), 1.18, f"{path.name}: grip radius varies too much (wrong pivot?)")
            self.assertLessEqual(max(rp) / min(rp), 1.18, f"{path.name}: plate radius varies too much (wrong pivot?)")

    def test_example_models_are_explicitly_labeled(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_site import is_example_record

        examples = []
        for path in sorted((ROOT / "catalog/machines").glob("*.json")):
            record = json.loads(path.read_text())
            detected = is_example_record(record)
            if detected:
                self.assertTrue(
                    record.get("example") is True,
                    f"{path.name} looks like a synthetic/unbranded example model and must set \"example\": true",
                )
                examples.append(path.stem)
        self.assertIn("innerscene-inclined-leg-press", examples)
        self.assertIn("single-arm-lever-curl", examples)
