from decimal import Decimal
import unittest

from fisher_agent.point_rules import historical_margin_passes, industry_margin_passes, operating_margin_pct


class PointRulesTests(unittest.TestCase):
    def test_pure_industry_rule_compares_percentage_points_without_rounding(self):
        self.assertTrue(industry_margin_passes(Decimal('20'), Decimal('20')))
        self.assertFalse(industry_margin_passes(Decimal('19.9999'), Decimal('20')))

    def test_pure_history_rule_requires_exact_years_and_strict_positivity(self):
        self.assertTrue(historical_margin_passes({2023: Decimal(20), 2024: Decimal(10), 2025: Decimal(20)}))
        self.assertFalse(historical_margin_passes({2023: Decimal(20), 2024: Decimal(0), 2025: Decimal(21)}))
        self.assertFalse(historical_margin_passes({2023: Decimal(20), 2024: Decimal(10), 2025: Decimal(19)}))
        with self.assertRaises(ValueError):
            historical_margin_passes({2023: Decimal(20), 2025: Decimal(20)})
        with self.assertRaises(ValueError):
            industry_margin_passes(Decimal('NaN'), Decimal(20))

    def test_operating_margin_includes_all_operating_costs(self):
        # Revenue 1000 less production 500, administration 200 and R&D 100.
        self.assertEqual(
            operating_margin_pct(Decimal('1000'), Decimal('800')),
            Decimal('20'),
        )

    def test_undefined_margin_rejects_zero_negative_or_nonfinite_inputs(self):
        for revenue, costs in [('0', '0'), ('-1', '0'), ('NaN', '1'),
                               ('Infinity', '1'), ('1', '-Infinity')]:
            with self.subTest(revenue=revenue, costs=costs):
                with self.assertRaises(ValueError):
                    operating_margin_pct(Decimal(revenue), Decimal(costs))

    def test_zero_and_negative_margins_are_valid_calculations(self):
        self.assertEqual(operating_margin_pct(Decimal(10), Decimal(10)), 0)
        self.assertEqual(operating_margin_pct(Decimal(10), Decimal(12)), -20)
