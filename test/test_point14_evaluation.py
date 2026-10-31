import unittest
from fisher_agent.point14.records import TransparencyResult
from evaluation.point14 import score_results


class EvaluationTests(unittest.TestCase):
    def test_semantic_abstentions_and_operational_errors_are_reported_separately(self):
        results = [TransparencyResult('unknown', status='insufficient_evidence'),
                   TransparencyResult('broken', status='api_error')]
        report = score_results(results, {name: {'points': {'14':'FAIL'}} for name in ('unknown','broken')})
        self.assertEqual(report['semantic_abstentions'], ['unknown'])
        self.assertEqual([r['company'] for r in report['operational_failures']], ['broken'])
        self.assertEqual(report['grounded_correct'], 0)
        self.assertEqual(report['public_adapter_correct'], 2)
        self.assertEqual(report['public_fallback_credit'], 2)

    def test_errors_do_not_count_as_grounded_correct_failures(self):
        results = [TransparencyResult('pass', verdict='PASS', status='assessed'),
                   TransparencyResult('fail', verdict='FAIL', status='assessed'),
                   TransparencyResult('error', status='api_error')]
        expected = {'pass': {'points': {'14': 'PASS'}}, 'fail': {'points': {'14':'FAIL'}},
                    'error': {'points': {'14':'FAIL'}}}
        report = score_results(results, expected)
        self.assertEqual(report['total_correct'], 2)
        self.assertEqual(report['pass_recall'], 1)
        self.assertEqual(report['fail_recall'], .5)
        self.assertEqual(report['balanced_accuracy'], .75)
        self.assertEqual(report['incorrect_companies'], ['error'])
        self.assertEqual(report['failures'][0]['status'], 'api_error')


class EvaluationDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_deadline_keeps_an_entry_for_queued_companies(self):
        from pathlib import Path
        from unittest.mock import patch
        from evaluation.point14 import evaluate
        with patch('evaluation.point14.BATCH_DEADLINE_SECONDS', 0), patch(
            'evaluation.point14.hw3.company_folders', return_value=[Path('synthetic')]
        ):
            report = await evaluate(Path('unused'), financial_only=True, concurrency=1)
        self.assertEqual(report['companies'], 1)
        self.assertEqual(report['complete'], 0)
        self.assertEqual(report['results'][0]['error_type'], 'BatchDeadline')

    async def test_tool_setup_failure_does_not_drop_other_companies(self):
        from pathlib import Path
        from unittest.mock import patch
        from evaluation.point14 import evaluate
        from test_point14_specialist import tools
        with patch('evaluation.point14.hw3.company_folders', return_value=[Path('bad'),Path('good')]), patch(
            'evaluation.point14.hw3.make_tools', side_effect=[ValueError('bad fixture'), tools()]
        ):
            report = await evaluate(Path('unused'), financial_only=True, concurrency=1)
        self.assertEqual(report['companies'], 2)
        self.assertEqual(report['complete'], 1)
        self.assertEqual(report['results'][0]['status'], 'error')
