import unittest

from benchmarks.run import run_benchmark


class TestBenchmark(unittest.TestCase):
    def test_public_synthetic_benchmark_is_reproducible(self):
        result = run_benchmark()

        self.assertEqual(result["sample_counts"]["feedback_events"], 4)
        self.assertEqual(result["sample_counts"]["scope_decisions"], 8)
        self.assertEqual(result["sample_counts"]["output_checks"], 12)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["error_generalization_rate"]["false_activations"], 0)
        self.assertEqual(result["violation_detection"]["true_positive"], 4)
        self.assertEqual(result["violation_detection"]["false_positive"], 0)
