"""Shared result boundary keeps operational errors separate from verdicts."""
import unittest

from fisher_agent.contracts import PointResult


class PointResultTests(unittest.TestCase):
    def test_operational_error_cannot_claim_an_investment_verdict(self):
        result = PointResult('sample', 4, None, 'error', 'Interview unavailable')
        self.assertIsNone(result.verdict)
        with self.assertRaises(ValueError):
            PointResult('sample', 4, 'FAIL', 'error', 'Interview unavailable')


if __name__ == '__main__':
    unittest.main()
