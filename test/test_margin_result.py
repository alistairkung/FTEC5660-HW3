from decimal import Decimal
import unittest

from fisher_agent.contracts import AnnualMargin, MarginResult, SQLEvidence


class MarginResultTests(unittest.TestCase):
    def test_completed_result_rejects_unresolved_or_cross_company_evidence(self):
        margin = AnnualMargin(2025, Decimal(1000), Decimal(800), Decimal(20), 'sql-1')
        for evidence in [SQLEvidence('sql-2', 'id', 'SELECT', 'raw'),
                         SQLEvidence('sql-1', 'other-company', 'SELECT', 'raw')]:
            with self.subTest(evidence=evidence):
                with self.assertRaises(ValueError):
                    MarginResult('id', 'industry', 'complete', 'PASS', 'Summary',
                                 (evidence,), (margin,))
