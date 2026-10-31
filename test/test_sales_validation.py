"""Deterministic provenance validation; semantics remain the model's responsibility."""
import unittest

from fisher_agent.sales_records import InterviewEvidence
from fisher_agent.result_validator import InvalidAssessment, validate_assessment


class SalesValidationTests(unittest.TestCase):
    def test_only_original_source_quotes_and_strict_contract_are_accepted(self):
        evidence = [InterviewEvidence('company', 'customer:sales_team', 'customer',
                                      'Their sales team explains the products clearly.')]
        valid = dict(verdict='PASS', evidence='explains the products clearly',
                     evidence_id='customer:sales_team', reasoning='Knowledgeable sales support.')
        self.assertEqual(validate_assessment(valid, evidence).verdict, 'PASS')
        for change in [dict(verdict='UNKNOWN'), dict(verdict=True), dict(evidence=3),
                       dict(evidence=''), dict(evidence='Products are cheap.'),
                       dict(evidence_id='supplier:sales_team'), dict(reasoning=' '),
                       dict(confidence=1)]:
            with self.subTest(change=change), self.assertRaises(InvalidAssessment):
                validate_assessment({**valid, **change}, evidence)

    def test_ambiguous_source_ids_cannot_select_evidence(self):
        evidence = [InterviewEvidence('a', 'customer:sales_team', 'customer', 'Excellent sales advice.'),
                    InterviewEvidence('b', 'customer:sales_team', 'customer', 'Excellent sales advice.')]
        with self.assertRaises(InvalidAssessment):
            validate_assessment(dict(verdict='PASS', evidence='Excellent sales advice.',
                                     evidence_id='customer:sales_team', reasoning='Knowledgeable support.'), evidence)
