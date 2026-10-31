"""Truth relations require alignment of the same sourced proposition."""
from dataclasses import replace
from decimal import Decimal
import unittest

from fisher_agent.point14.claim_evidence_matcher import match_claim, MEASUREMENT_DEFINITIONS
from fisher_agent.point14.records import EvidenceFact, ManagementClaim, SourcedProposition


def claim(metric='revenue', **changes):
    proposition = SourcedProposition('company', metric, '2026Q1', 'level',
                                    Decimal('265.7'), 'USD_millions', 'level', certainty='asserted',
                                    measurement_definition=MEASUREMENT_DEFINITIONS.get(metric))
    proposition = replace(proposition, **changes)
    return ManagementClaim('claim:1', 'call.md', '2026Q1', 'revenue',
                           'Revenue was USD 265.7 million.', 'favourable', proposition,
                           company_id='synthetic', source_id='doc:1', speaker='CEO')


def fact(metric='revenue', **changes):
    result = EvidenceFact('fact:1', 'synthetic', 'company', metric, '2026Q1',
                          'level', Decimal('248068'), 'USD_thousands', 'sql:1',
                          measurement_definition=MEASUREMENT_DEFINITIONS.get(metric))
    return replace(result, **changes)


class MatchingTests(unittest.TestCase):
    def test_numeric_disagreement_is_retained_only_for_aligned_revenue(self):
        result = match_claim(claim(), fact())
        self.assertEqual(result.compatibility, 'COMPATIBLE')
        self.assertEqual(result.relation, 'CONTRADICTED')
        self.assertEqual(result.claim_id, 'claim:1')
        self.assertEqual(result.fact_id, 'fact:1')

    def test_returns_admission_cannot_be_contradicted_by_profit(self):
        admission = claim('return_rate', assertion_type='change', value=None,
                          unit='percent', basis=None, direction='increased')
        result = match_claim(admission, fact('operating_profit'))
        self.assertEqual(result.relation, 'UNMATCHED')
        self.assertEqual(result.compatibility, 'INCOMPATIBLE')

    def test_wrong_subject_period_comparator_or_unit_never_creates_contradiction(self):
        for change in ({'subject': 'specific_product'}, {'period': '2025Q4'},
                       {'unit': 'units'}, {'basis': 'qoq', 'comparator_period': '2025Q4'}):
            with self.subTest(change=change):
                self.assertIn(match_claim(claim(**change), fact()).relation,
                              ('UNMATCHED', 'INCONCLUSIVE'))

    def test_equivalent_units_and_declared_reporting_precision_match(self):
        reported = claim(value=Decimal('229.2'))
        actual = fact(value=Decimal('229152.60'))
        self.assertEqual(match_claim(reported, actual).relation, 'SUPPORTED')
        self.assertEqual(match_claim(claim(value=Decimal('229200'), unit='USD_thousands'),
                                    fact(value=Decimal('229200'))).relation, 'SUPPORTED')

    def test_low_returns_has_direct_measurement_but_no_invented_threshold(self):
        low = claim('return_rate', value=None, unit='percent', direction='low')
        measured = fact('return_rate', value=Decimal(378) / Decimal(7432) * 100, unit='percent')
        result = match_claim(low, measured)
        self.assertEqual(result.compatibility, 'COMPATIBLE')
        self.assertEqual(result.relation, 'INCONCLUSIVE')
        self.assertIn('criterion', result.reason)

    def test_unknown_comparator_or_certainty_stays_inconclusive(self):
        changed = claim('return_rate', value=None, unit='percent', assertion_type='change',
                        basis=None, direction='increased')
        measured = fact('return_rate', unit='percent', basis='qoq', comparator_period='2025Q4',
                        value=Decimal('5.09'), absolute_change=Decimal('3.4'))
        self.assertEqual(match_claim(changed, measured).relation, 'INCONCLUSIVE')
        self.assertEqual(match_claim(claim(certainty='unknown'), fact()).relation, 'INCONCLUSIVE')

    def test_change_still_requires_compatible_units_and_numeric_assertion_type(self):
        changed = claim('return_rate', value=None, unit='USD_millions', assertion_type='change',
                        basis='qoq', comparator_period='2025Q4', direction='increased')
        measured = fact('return_rate', unit='percent', basis='qoq', comparator_period='2025Q4',
                        value=Decimal('5.09'), absolute_change=Decimal('3.4'))
        self.assertEqual(match_claim(changed, measured).relation, 'UNMATCHED')
        self.assertEqual(match_claim(claim(assertion_type='event'), fact()).relation, 'INCONCLUSIVE')

    def test_positive_decline_magnitudes_and_explicit_negative_changes_are_supported(self):
        for unit, value, actual_delta, actual_percentage, direction in (
            ('percent', '5', '-5', '-5', 'decreased'),
            ('percent', '-5', '-5', '-5', 'decreased'),
            ('USD_millions', '5', '-5000', '-5', 'decreased'),
            ('percentage_points', '5', '-5', '-20', 'decreased'),
        ):
            margin = unit == 'percentage_points'
            reported = claim('operating_margin_pct' if margin else 'revenue', assertion_type='change',
                value=Decimal(value), unit=unit, basis='qoq', comparator_period='2025Q4', direction=direction)
            measured = fact('operating_margin_pct' if margin else 'revenue', basis='qoq',
                comparator_period='2025Q4', unit='percent' if margin else 'USD_thousands',
                absolute_change=Decimal(actual_delta), percentage_change=Decimal(actual_percentage))
            with self.subTest(unit=unit, value=value):
                self.assertEqual(match_claim(reported, measured).relation, 'SUPPORTED')

    def test_ratio_definition_is_required_and_must_match_the_same_measurement(self):
        measured = fact('return_rate', value=Decimal('5'), unit='percent')
        refund_ratio = claim('return_rate', value=Decimal('2'), unit='percent',
                             measurement_definition='refund_amount/revenue')
        self.assertEqual(match_claim(refund_ratio, measured).relation, 'UNMATCHED')
        unknown = claim('return_rate', value=Decimal('2'), unit='percent', measurement_definition=None)
        self.assertEqual(match_claim(unknown, measured).relation, 'INCONCLUSIVE')

    def test_qualitative_stable_has_no_invented_exact_zero_tolerance(self):
        reported = claim(assertion_type='change', value=None, unit='USD_thousands', basis='qoq',
                         comparator_period='2025Q4', direction='stable')
        measured = fact(basis='qoq', comparator_period='2025Q4', absolute_change=Decimal('0.01'))
        self.assertEqual(match_claim(reported, measured).relation, 'INCONCLUSIVE')
