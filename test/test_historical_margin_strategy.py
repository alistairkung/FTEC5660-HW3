import unittest

from fisher_agent.point5.margin_records import MarginResult, MarginStrategy
from fisher_agent.point5.historical_margin_strategy import HistoricalMarginStrategy
from fisher_agent.point5.industry_margin_strategy import IndustryMarginStrategy
from test_industry_margin_strategy import FakeSQL, annual


class HistoricalMarginStrategyTests(unittest.TestCase):
    def test_positive_three_year_history_with_flat_endpoint_passes(self):
        result = HistoricalMarginStrategy().evaluate('id', FakeSQL(annual(
            (2023, 1000, 800), (2024, 1000, 900), (2025, 1000, 800))))
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual([item.margin_pct for item in result.margins], [20, 10, 20])
        self.assertIsNone(result.industry_median_pct)

    def test_nonpositive_year_or_declining_endpoint_fails(self):
        for costs in [(800, 1000, 700), (800, 1001, 700), (800, 700, 801),
                      (1000, 900, 800), (800, 900, 1000)]:
            with self.subTest(costs=costs):
                result = HistoricalMarginStrategy().evaluate('id', FakeSQL(annual(
                    *[(year, 1000, cost) for year, cost in zip((2023, 2024, 2025), costs)])))
                self.assertEqual(result.verdict, 'FAIL')

    def test_missing_middle_year_is_an_error_not_a_fail(self):
        result = HistoricalMarginStrategy().evaluate('id', FakeSQL(annual(
            (2023, 1000, 800), (2025, 1000, 800))))
        self.assertEqual(result.status, 'error')
        self.assertIsNone(result.verdict)

    def test_strategies_are_interchangeable_and_keep_company_state_separate(self):
        strategies: list[MarginStrategy] = [IndustryMarginStrategy(), HistoricalMarginStrategy()]
        for strategy in strategies:
            for company in ('company-a', 'company-b'):
                with self.subTest(strategy=strategy.name, company=company):
                    tool = FakeSQL(annual((2025, 1000, 800)),
                                   'industry | operating_margin_pct\nmedical | 20')
                    if strategy.name == 'historical':
                        tool = FakeSQL(annual((2023, 1000, 800), (2024, 1000, 800),
                                              (2025, 1000, 800)))
                    result = strategy.evaluate(company, tool)
                    self.assertIsInstance(result, MarginResult)
                    self.assertEqual(result.company_id, company)
                    self.assertEqual(result.verdict, 'PASS')
                    self.assertTrue(all(item.company_id == company for item in result.evidence))
