import unittest

from resistance_curves import evaluate_curve, fit_curve


class CurveTests(unittest.TestCase):
    def test_polynomial_degree_and_endpoint_constraints(self):
        for coefficients in ([0], [0.5], [0.8, -0.2], [1, 1, -1], [1, 0, 0, 1]):
            points = []
            for i in range(21):
                x = i / 20
                points.append([x, sum(c * x**p for p, c in enumerate(coefficients))])
            curve = fit_curve(points)
            self.assertEqual(curve["type"], "polynomial")
            self.assertEqual(len(curve["coefficients"]), len(coefficients))
            for x, y in points:
                self.assertAlmostEqual(evaluate_curve(curve, x), y)
        with self.assertRaises(ValueError):
            evaluate_curve(curve, 1.01)

    def test_spline_preserves_local_range_on_uneven_knots(self):
        points = [[0, 0], [.21, 1.1], [.23, 0], [.5, .1], [.52, 1.4], [1, 0]]
        curve = fit_curve(points)
        self.assertEqual(curve["type"], "pchip")
        for x, y in points:
            self.assertAlmostEqual(evaluate_curve(curve, x), y)
        for (a, y), (b, z) in zip(points, points[1:]):
            for i in range(21):
                value = evaluate_curve(curve, a + (b-a) * i / 20)
                self.assertGreaterEqual(value, min(y,z) - 1e-9)
                self.assertLessEqual(value, max(y,z) + 1e-9)

    def test_sparse_fit_rejects_overshooting_polynomial(self):
        # An interpolating quadratic would exceed the flat interval.
        curve = fit_curve([[0, 0], [.1, 1], [1, 1]])
        self.assertEqual(curve["type"], "pchip")
        self.assertEqual(evaluate_curve(curve, .5), 1)

    def test_bad_samples(self):
        for points in ([[0, 1], [0, 2]], [[0, 1], [1, -1]], [[0, 1], [.5, 2]]):
            with self.assertRaises(ValueError):
                fit_curve(points)
