import unittest

from evaluation.combined import score_results
from fisher_agent.company_analyzer import CompanyAssessment
from fisher_agent.contracts import PointResult, ProvenanceReference


class CombinedEvaluationTests(unittest.TestCase):
    def test_operational_fallback_credit_is_separate_and_never_grounded_accuracy(self):
        source = ProvenanceReference('sql-1', 'sample', 'sql_query')
        result = CompanyAssessment('sample', {
            4: PointResult('sample', 4, None, 'error', 'Model unavailable'),
            5: PointResult('sample', 5, 'PASS', 'complete', 'Above median', (source,)),
            14: PointResult('sample', 14, None, 'pending', 'Point 14 pending'),
        })
        metrics = score_results({'sample': result},
                                {'sample': {'points': {'4': 'FAIL', '5': 'PASS', '14': 'PASS'}}})
        self.assertEqual(metrics['4']['grounded_correct'], 0)
        self.assertEqual(metrics['4']['fallback_credits'], 1)
        self.assertEqual(metrics['4']['balanced_accuracy'], 0)
        self.assertEqual(metrics['5']['grounded_correct'], 1)
