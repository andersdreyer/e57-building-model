import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "e57_model.py"
SPEC = importlib.util.spec_from_file_location("e57_model", MODULE_PATH)
e57_model = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = e57_model
SPEC.loader.exec_module(e57_model)


class AxisRecommendationTests(unittest.TestCase):
    def test_recommends_orthogonal_lock_for_consistent_walls(self):
        import numpy as np

        planes = [
            {"classification": "vertical", "normal_azimuth_deg": 7.4, "inlier_points": 1000},
            {"classification": "vertical", "normal_azimuth_deg": 7.6, "inlier_points": 900},
            {"classification": "vertical", "normal_azimuth_deg": 97.5, "inlier_points": 1100},
            {"classification": "vertical", "normal_azimuth_deg": 97.6, "inlier_points": 950},
        ]

        result = e57_model.axis_recommendation(planes, np)

        self.assertTrue(result["recommend_orthogonal_lock"])
        self.assertAlmostEqual(result["primary_axis_deg"], 7.5, delta=0.2)

    def test_requires_review_for_inconsistent_walls(self):
        import numpy as np

        planes = [
            {"classification": "vertical", "normal_azimuth_deg": 0.0, "inlier_points": 1000},
            {"classification": "vertical", "normal_azimuth_deg": 31.0, "inlier_points": 1000},
            {"classification": "vertical", "normal_azimuth_deg": 82.0, "inlier_points": 1000},
        ]

        result = e57_model.axis_recommendation(planes, np)

        self.assertFalse(result["recommend_orthogonal_lock"])
        self.assertEqual(result["decision"], "review_before_locking")


class ProfileTests(unittest.TestCase):
    def test_rejects_unsupported_custom_resolution_without_override(self):
        analysis = {"spacing": {"median_m": 0.02}}
        args = Namespace(
            profile="custom",
            resolution_mm=10.0,
            target_triangles=100_000,
            allow_unsupported_resolution=False,
        )

        with self.assertRaises(SystemExit):
            e57_model.profile_from_args(analysis, args)

    def test_accepts_custom_resolution_with_override(self):
        analysis = {"spacing": {"median_m": 0.02}}
        args = Namespace(
            profile="custom",
            resolution_mm=10.0,
            target_triangles=100_000,
            allow_unsupported_resolution=True,
        )

        profile = e57_model.profile_from_args(analysis, args)

        self.assertEqual(profile["name"], "custom")
        self.assertEqual(profile["target_triangles"], 100_000)


class PlanRegistrationTests(unittest.TestCase):
    def test_similarity_registration_records_low_residual(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            manifest_path = directory_path / "constraints.json"
            output_path = directory_path / "registered.json"
            manifest = {
                "reference_plans": [
                    {
                        "transform": "similarity",
                        "tolerance_m": 0.01,
                        "control_points": [
                            {"plan_xy": [0.0, 0.0], "scan_xy": [100.0, 50.0]},
                            {"plan_xy": [10.0, 0.0], "scan_xy": [109.91445, 51.30526]},
                            {"plan_xy": [0.0, 5.0], "scan_xy": [99.34737, 54.95722]},
                        ],
                    }
                ]
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            status = e57_model.register_plan(
                Namespace(
                    input=str(manifest_path),
                    output=str(output_path),
                    plan_index=0,
                    tolerance_m=0.05,
                )
            )

            result = json.loads(output_path.read_text(encoding="utf-8"))
            registration = result["reference_plans"][0]["registration"]
            self.assertEqual(status, 0)
            self.assertEqual(registration["status"], "within_tolerance")
            self.assertLess(registration["max_residual_m"], 0.0001)


if __name__ == "__main__":
    unittest.main()
