from decimal import Decimal
import unittest

from fisher_agent.point5.industry_margin_strategy import IndustryMarginStrategy


ANNUAL_HEADER = ('year | revenue | operating_costs | order_count | invalid_orders | '
                 'cost_rows | cost_months | invalid_costs')


class FakeSQL:
    name = 'sql_query'

    def __init__(self, *responses):
        self.responses = iter(responses)
        self.queries = []

    def invoke(self, arguments):
        self.queries.append(arguments['query'])
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def annual(*rows):
    return ANNUAL_HEADER + '\n' + '\n'.join(
        f'{year} | {revenue} | {costs} | 100 | 0 | 12 | 12 | 0'
        for year, revenue, costs in rows)


class IndustryMarginStrategyTests(unittest.TestCase):
    def test_missing_or_invalid_matching_median_never_becomes_fail(self):
        for median in ['industry | operating_margin_pct\n(no rows)',
                       'industry | operating_margin_pct\nmedical | None',
                       'industry | operating_margin_pct\nmedical | NaN',
                       'industry | operating_margin_pct\nmedical | 20\nmedical | 30',
                       'SQL error: no such table']:
            with self.subTest(median=median):
                result = IndustryMarginStrategy().evaluate(
                    'id', FakeSQL(annual((2025, 1000, 800)), median))
                self.assertEqual(result.status, 'error')
                self.assertIsNone(result.verdict)
                self.assertEqual(len(result.evidence), 2)

    def test_industry_threshold_uses_unrounded_percentage_points(self):
        for costs, median, expected in [('800.01', '20', 'FAIL'),
                                         ('799.99', '20', 'PASS'),
                                         ('1200', '-20', 'PASS')]:
            with self.subTest(costs=costs, median=median):
                result = IndustryMarginStrategy().evaluate('id', FakeSQL(
                    annual((2025, 1000, costs)),
                    f'industry | operating_margin_pct\nmedical | {median}'))
                self.assertEqual(result.verdict, expected)

    def test_invalid_evidence_produces_an_error_without_an_investment_verdict(self):
        valid = annual((2025, 1000, 800))
        bad_results = [
            ('SQL error: database unavailable', 'sql_error'),
            (RuntimeError('tool unavailable'), 'sql_error'),
            ('', 'invalid_result'),
            (None, 'invalid_result'),
            (ANNUAL_HEADER + '\n(no rows)', 'missing_data'),
            (ANNUAL_HEADER, 'missing_data'),
            (valid + '\n... more rows not shown (limit 50); aggregate.', 'truncated_result'),
            (valid.replace('1000', '0'), 'invalid_number'),
            (valid.replace('800', 'NaN'), 'invalid_number'),
            (valid.replace('800', 'inf'), 'invalid_number'),
            (valid.replace('800', 'None'), 'invalid_number'),
            (valid.replace('800', 'eight hundred'), 'invalid_number'),
            (valid.replace(' | 100 | 0 |', ' | 100 | 1 |'), 'invalid_number'),
            (valid.replace(' | 12 | 12 |', ' | 11 | 11 |'), 'missing_data'),
            (valid.replace(' | 12 | 12 |', ' | 13 | 12 |'), 'missing_data'),
            (valid.replace('2025', '2024'), 'missing_data'),
            (valid + '\n' + valid.splitlines()[1], 'missing_data'),
            (valid.rsplit('|', 1)[0] + '| 1', 'invalid_number'),
        ]
        for raw, code in bad_results:
            with self.subTest(raw=raw):
                result = IndustryMarginStrategy().evaluate('id', FakeSQL(raw))
                self.assertEqual(result.status, 'error')
                self.assertIsNone(result.verdict)
                self.assertEqual(result.error.code, code)
                self.assertEqual(len(result.evidence), 1)

    def test_margin_equal_to_matching_industry_median_passes_with_provenance(self):
        tool = FakeSQL(annual((2025, 1000, 800)),
                       'industry | operating_margin_pct\nmedical | 20.00')
        result = IndustryMarginStrategy().evaluate('arbitrary-id', tool)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(result.status, 'complete')
        self.assertEqual(result.margins[0].margin_pct, Decimal('20'))
        self.assertEqual(result.industry_median_pct, Decimal('20'))
        self.assertEqual(result.evidence[0].raw_result, annual((2025, 1000, 800)))
        self.assertEqual(result.margins[0].evidence_id, result.evidence[0].evidence_id)
        self.assertEqual(result.evidence[1].company_id, 'arbitrary-id')
        self.assertIn('company', tool.queries[1])
        self.assertIn('industry_medians', tool.queries[1])
