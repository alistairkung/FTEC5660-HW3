import unittest

from fisher_agent.point_adapters import adapt_sales, adapt_margin
from fisher_agent.sales_records import InterviewEvidence, SalesAssessment, SalesResult
from fisher_agent.industry_margin_strategy import IndustryMarginStrategy
from test_industry_margin_strategy import FakeSQL


class PointAdapterTests(unittest.TestCase):
    def test_sales_operational_fail_becomes_no_verdict_not_supported_fail(self):
        result = adapt_sales(SalesResult('sample', status='api_error'))
        self.assertIsNone(result.verdict)
        self.assertEqual(result.status, 'error')

    def test_supported_sales_retains_quote_and_provenance(self):
        source = InterviewEvidence('sample', 'customer:sales_team', 'customer', 'Slow replies.')
        finding = SalesAssessment(verdict='FAIL', evidence='Slow replies.',
                                  evidence_id=source.evidence_id, reasoning='Poor response.')
        raw = SalesResult('sample', 'FAIL', evidence=[source], assessments=[finding])
        result = adapt_sales(raw)
        self.assertEqual(result.verdict, 'FAIL')
        self.assertEqual(result.status, 'complete')
        self.assertEqual(result.provenance[0].evidence_id, source.evidence_id)
        self.assertIn('Slow replies.', result.summary)

    def test_margin_sql_error_has_no_verdict(self):
        raw = IndustryMarginStrategy().evaluate('sample', FakeSQL('SQL error: unavailable'))
        result = adapt_margin(raw)
        self.assertIsNone(result.verdict)
        self.assertEqual(result.diagnostics[0].code, 'sql_error')
