import json
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

import numpy as np

from resistance_curves.mechanics import estimate
from resistance_curves.models3d import model_observation, prepare_models


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"center_m": [0, 0, 0], "px_per_m": 250,
                         "right": "x", "up": "y", "source": "test model",
                         "assets": [{"file": "pose.glb", "parts": []}]}

    def test_sled_uses_full_spatial_length(self):
        result = model_observation(self.manifest, {
            "mechanism": "sled", "evidence": "Rail direction known.",
            "poses": [{"rail_low": [0, 0, 0], "rail_high": [0, 0.6, 0.8]}]})
        self.assertAlmostEqual(estimate(result, 20)["samples"][0]["force_kgf"], 12)

    def test_single_lever_requires_evidenced_sweep(self):
        marks = {"mechanism": "lever", "evidence": "Documented 60 degree CCW stroke.",
                 "poses": [{"pivot": [0, 0, 0], "plates": [1, 0, 0], "grip": [0.5, 0, 0]}]}
        with self.assertRaisesRegex(ValueError, "sweep_deg"):
            model_observation(self.manifest, marks)
        marks["sweep_deg"] = -60
        result = estimate(model_observation(self.manifest, marks), 10)
        self.assertAlmostEqual(result["samples"][0]["force_kgf"], 20)
        self.assertAlmostEqual(result["samples"][-1]["force_kgf"], 10)

    def test_cam_needs_distinct_geometry(self):
        marks = {"mechanism": "belt_cam", "evidence": "One static pose.", "space": "side_pixels",
                 "poses": [dict.fromkeys(("pivot", "plates", "cam_pivot", "grip", "belt_cam", "belt_load"), [100, 200])]}
        with self.assertRaisesRegex(ValueError, "two poses"):
            model_observation(self.manifest, marks)

    @unittest.skipUnless(find_spec("trimesh"), "install the models extra for mesh import tests")
    def test_formats_and_instances(self):
        import trimesh

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            box = trimesh.creation.box(extents=[1, 2, 3])
            for ext in ("obj", "stl", "gltf", "glb"):
                with self.subTest(ext=ext):
                    scene = trimesh.Scene()
                    matrix = np.eye(4)
                    matrix[0, 3] = 2
                    scene.add_geometry(box, node_name="mover", transform=matrix)
                    path = root / f"machine.{ext}"
                    if ext in ("obj", "stl"):
                        box.export(path)
                        with self.assertRaisesRegex(ValueError, "units"):
                            prepare_models([path], root / "bad", source="fixture")
                    else:
                        scene.export(path)
                    out = root / ext
                    metric = ext in ("glb", "gltf")
                    manifest = prepare_models([path], out, source="fixture", units=None if metric else "mm")
                    self.assertTrue((out / "end-001.jpg").is_file())
                    self.assertEqual(json.loads((out / "model.json").read_text()), manifest)
                    if metric:
                        pose = {"rail_low": {"node": "mover", "local": [0, -1, 0]},
                                "rail_high": {"node": "mover", "local": [0, 1, 0]}}
                        obs = model_observation(manifest, {"mechanism": "sled", "evidence": "test",
                                                           "poses": [pose]})
                        self.assertEqual(obs["model_source"]["world_m"][0]["rail_low"], [2, -1, 0])
                    else:
                        self.assertAlmostEqual(manifest["assets"][0]["parts"][0]["bounds_m"][1][0], .0005)
