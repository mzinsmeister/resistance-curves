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
