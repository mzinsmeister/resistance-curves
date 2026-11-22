import json
from pathlib import Path
import unittest

from resistance_curves.catalog import machine_view

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

    def test_benchmark_stays_sparse(self):
        data = json.loads((ROOT / "catalog/machines/hammer-strength-preacher-curl.json").read_text())
        v = machine_view(data)
        self.assertEqual(len(v["points"]), 2)
        self.assertEqual(v["geometry"], [])


    def test_video_work_is_invariant_to_camera_translation(self):
        from resistance_curves.work_check import motion_work_check

        poses = [
            dict(anchor=[50, 60], plates=[10, 80], hand=[100, 30], handle_cap=[100, 30]),
            dict(anchor=[55, 70], plates=[15, 70], hand=[105, 15], handle_cap=[105, 10]),
        ]
        result = motion_work_check(poses)
        self.assertAlmostEqual(result["hand_kgf_per_kg"], 20/25)
        self.assertAlmostEqual(result["handle_cap_kgf_per_kg"], 20/30)

    def test_splbc_interval_means_preserve_total_work(self):
        from resistance_curves.curves import evaluate_curve

        record = json.loads((ROOT / "catalog/machines/life-fitness-signature-biceps-curl.json").read_text())
        data = machine_view(record)
        self.assertEqual(data["points"], [])
        curve = data["resistance_curve"]
        self.assertEqual(curve["type"], "interval_mean")
        mean = sum((b-a) * evaluate_curve(curve, (a+b)/2)
                   for a, b in zip(curve["knots"], curve["knots"][1:]))
        self.assertAlmostEqual(mean, 110/162.07112629)
        self.assertAlmostEqual(mean, data["motion_evidence"]["mean_kgf_per_kg"])
        self.assertAlmostEqual(evaluate_curve(curve, 1), curve["coefficients"][-1][0])
        record["motion_observation"]["poses"].reverse()
        with self.assertRaisesRegex(ValueError, "ascending"):
            machine_view(record)

    def test_catalog_starting_resistance(self):
        record = json.loads((ROOT / "catalog/machines/hammer-strength-preacher-curl.json").read_text())
        self.assertFalse(machine_view(record)["reference_includes_base"])
        del record["reference_includes_base"]
        self.assertTrue(machine_view(record)["reference_includes_base"])
        self.assertEqual(machine_view(record)["base_resistance"]["starting_kgf"], 2)
        record["base_resistance"]["starting_kgf"] = -1
        with self.assertRaisesRegex(ValueError, "Base resistance"):
            machine_view(record)
