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
        data = {"mechanism": "lever", "poses": [pose([570.71, 570.71]), pose([500, 400])]}
        profile = estimate(data)
        self.assertAlmostEqual(profile["samples"][100]["newtons_per_kg"], 0)
        self.assertGreater(profile["samples"][33]["newtons_per_kg"], 9.80)

    def test_sled_constant(self):
        pose = {"rail_low": [100, 500], "rail_high": [400, 100]}
        profile = estimate({"mechanism": "sled", "poses": [pose, pose]}, 15)
        self.assertEqual([p["force_kgf"] for p in profile["samples"]], [12, 12])

    def test_chain_pulled_lever_uses_pull_line_and_both_plate_stations(self):
        start = {"pivot": [300, 300], "grip": [100, 400], "pull_toward": [100, 200],
                 "plates": [200, 340], "secondary_plates": [250, 320]}
        finish = {"pivot": [300, 300], "grip": [76, 300], "pull_toward": [76, 100],
                  "plates": [193, 291], "secondary_plates": [246, 295]}
        data = {"mechanism": "lever", "secondary_plate_fraction": 0.25,
                "poses": [start, finish]}
        profile = estimate(data, 20)
        self.assertAlmostEqual(profile["samples"][0]["force_kgf"], 20 * 87.5 / 200)
        self.assertAlmostEqual(profile["samples"][1]["force_kgf"], 20 * 93.75 / 224)
        start["pull_toward"] = [100, 550]
        with self.assertRaisesRegex(ValueError, "opposing moment"):
            estimate(data)

    def test_belt_cam_with_pivoting_handle_pull_line_and_anatomy(self):
        example = json.loads(EXAMPLE.read_text())
        for pose in example["poses"]:
            # Add a pivoting handle line at 60 deg to the rigid cam arm (grip -> pull_toward)
            gx, gy = pose["grip"]
            pose["pull_toward"] = [gx + 50, gy - 86.6025403784]
            pose["joint"] = [pose["cam_pivot"][0] + 60, pose["cam_pivot"][1]]
            pose["proximal"] = [pose["cam_pivot"][0] + 60, pose["cam_pivot"][1] - 100]
            pose["distal"] = [gx + 50, gy - 86.6025403784]
            pose["scale_start"] = [0, 0]
            pose["scale_end"] = [100, 0]
            pose["scale_m"] = 0.2
            pose["scale_source"] = "Unit test scale"
        profile = estimate(example, 20)
        p0 = profile["poses"][0]
        # cam_arm = 60, tension = 240/150 = 1.6, pull_arm = moment_arm(cam_pivot, grip, pull_toward)
        expected_arm = moment_arm(example["poses"][0]["cam_pivot"], example["poses"][0]["grip"], example["poses"][0]["pull_toward"])
        self.assertAlmostEqual(p0["pull_arm_px"], expected_arm)
        self.assertAlmostEqual(p0["contact_force_kgf"], 20 * (240 / 150) * (60 / expected_arm))
        expected_joint_arm = abs(moment_arm(example["poses"][0]["joint"], example["poses"][0]["grip"], example["poses"][0]["pull_toward"])) * 0.2 / 100
        self.assertAlmostEqual(p0["joint_arm_m"], expected_joint_arm)
        # Reversed pull direction should fail
        example["poses"][0]["pull_toward"] = [example["poses"][0]["grip"][0] - 50, example["poses"][0]["grip"][1] + 86.6]
        with self.assertRaisesRegex(ValueError, "opposing moment"):
            estimate(example)

    def test_belt_cam_rejects_non_rigid_grip_and_drifting_plates(self):
        example = json.loads(EXAMPLE.read_text())
        # Inflate cam->grip radius by >15% (simulating a pivoting handle mistakenly marked as rigid)
        bad_grip = json.loads(json.dumps(example))
        bad_grip["poses"][1]["grip"] = [210, 210]
        with self.assertRaisesRegex(ValueError, "Cam-to-grip radius"):
            estimate(bad_grip)
        # Drift pivot->plates radius by >15% (simulating inconsistent plate-hub tracking / obliquity)
        bad_plates = json.loads(json.dumps(example))
        bad_plates["poses"][1]["plates"] = [150, 700]
        with self.assertRaisesRegex(ValueError, "Load-pivot-to-plates radius"):
            estimate(bad_plates)

    def test_lever_rejects_wrong_pivot_even_when_radius_ratio_stays_constant(self):
        # True pivot is [500, 500], arm swings 60 deg with r_grip=150, r_plates=150;
        # shifting pivot to a bogus [460, 460] keeps radius_ratio ~1.0 while both radii vary by >20%.
        poses = []
        for deg in (30, 0, -30):
            rad = math.radians(deg)
            pt = [500 + 150 * math.cos(rad), 500 + 150 * math.sin(rad)]
            poses.append({"pivot": [440, 440], "plates": pt, "grip": pt})
        with self.assertRaisesRegex(ValueError, "Lever arm radius varies"):
            estimate({"mechanism": "lever", "poses": poses})

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
