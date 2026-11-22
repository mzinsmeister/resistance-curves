import json
import math
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from resistance_curves import estimate, moment_arm, tangential_force
from resistance_curves.__main__ import run_estimate
from resistance_curves.vision import prepare

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/belt-cam.json"


class MechanicsTests(unittest.TestCase):
    def test_cam_stage_from_worked_example_in_metric(self):
        # Metric equivalents of the slide's tension and perpendicular arms.
        self.assertAlmostEqual(tangential_force(533.7865938, 0.1016, 0.254), 213.51463752)

    def test_belt_uses_perpendicular_distance(self):
        self.assertAlmostEqual(moment_arm((0, 0), (0, 10), (10, 20)), -10 / math.sqrt(2))
        profile = estimate(json.loads(EXAMPLE.read_text()), 20)
        self.assertAlmostEqual(profile["poses"][0]["tension_per_plate_weight"], 240 / 150)
        self.assertAlmostEqual(profile["samples"][0]["force_kgf"], 20 * 240 / 150 * 60 / 150)
        self.assertEqual(len(profile["samples"]), 2)

    def test_slack_belt(self):
        example = json.loads(EXAMPLE.read_text())
        example["poses"][0]["plates"][0] = 700
        with self.assertRaisesRegex(ValueError, "push"):
            estimate(example)

    def test_rigid_arm_has_interior_peak_and_zero_at_vertical(self):
        pose = lambda point: {"pivot": [500, 500], "plates": point, "grip": point}
        data = {"mechanism": "lever", "poses": [pose([600, 600]), pose([500, 400])]}
        profile = estimate(data)
        self.assertAlmostEqual(profile["samples"][100]["newtons_per_kg"], 0)
        self.assertGreater(profile["samples"][33]["newtons_per_kg"], 9.80)

    def test_sled_constant(self):
        pose = {"rail_low": [100, 500], "rail_high": [400, 100]}
        profile = estimate({"mechanism": "sled", "poses": [pose, pose]}, 15)
        self.assertEqual([p["force_kgf"] for p in profile["samples"]], [12, 12])

    def test_unresolved(self):
        with self.assertRaisesRegex(ValueError, "hidden pivot"):
            estimate({"mechanism": "unresolved", "evidence": "hidden pivot"})

    def test_vision_workflow(self):
        observation = json.loads(EXAMPLE.read_text())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "wide.jpg"
            Image.new("RGB", (600, 300), "red").save(src)
            views = prepare([src, src], root / "session")
            with Image.open(views[0]) as photo:
                self.assertEqual(photo.size, (1000, 1000))
                self.assertGreater(photo.getpixel((0, 0))[1], 250)
            run_estimate(observation, views, 10, root / "result")
            for name in ("profile.json", "profile.png", "landmarks-001.png", "landmarks-002.png"):
                self.assertTrue((root / "result" / name).is_file())
