"""Development scoring counts operational fallback matches separately."""
import unittest
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fisher_agent.sales_records import SalesResult
from evaluation.point4 import evaluate, score_results
from fisher_agent.evidence_interpreter import EvidenceInterpreter
from fisher_agent.sales_specialist import SalesSpecialist
from test_sales_specialist import ScriptedModel, decision, interviews


class Point4EvaluationTests(unittest.TestCase):
    def test_balanced_recall_and_failures_are_reported_separately(self):
        results = {
            'positive': SalesResult('positive', verdict='PASS'),
            'missed': SalesResult('missed', verdict='FAIL'),
            'negative': SalesResult('negative', verdict='FAIL'),
            'failed': SalesResult('failed', verdict='FAIL', status='api_error'),
        }
        labels = {name: {'points': {'4': verdict}} for name, verdict in
                  [('positive', 'PASS'), ('missed', 'PASS'), ('negative', 'FAIL'), ('failed', 'FAIL')]}
        score = score_results(results, labels)
        self.assertEqual(score['correct'], 3)
        self.assertEqual(score['pass_recall'], 0.5)
        self.assertEqual(score['fail_recall'], 1.0)
        self.assertEqual(score['balanced_accuracy'], 0.75)
        self.assertEqual(score['misclassified'], ['missed'])
        self.assertEqual(score['successful_assessments'], 3)
        self.assertEqual(score['grounded_correct'], 2)
        self.assertEqual(score['failures'], ['failed'])

    def test_missing_labels_are_rejected_instead_of_silently_dropping_companies(self):
        with self.assertRaises(ValueError):
            score_results({'unlabelled': SalesResult('unlabelled')}, {})


class Point4RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_saves_auditable_predictions_then_reads_labels(self):
        model = ScriptedModel(responses=[decision()])
        specialist = SalesSpecialist(EvidenceInterpreter(model))
        tools, calls = interviews()

        def labels(_):
            self.assertEqual(len(model.seen), 1)
            return {'synthetic': {'points': {'4': 'PASS'}}}

        with TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'synthetic').mkdir()
            output = folder / 'report.json'
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake',
                                         'LANGFUSE_TRACING_ENABLED': 'false'}), \
                    patch('evaluation.point4.hw3.make_tools', return_value=tools), \
                    patch('evaluation.point4.hw3.INTERVIEWS_USED', {'synthetic': 1}), \
                    patch('evaluation.point4.hw3.read_ground_truth', side_effect=labels), \
                    patch('evaluation.point4.build_sales_specialist', return_value=specialist):
                report = await evaluate(folder, output)
            saved = json.loads(output.read_text())
            self.assertTrue(report['live_evaluation_complete'])
            self.assertEqual(saved['metrics']['correct'], 1)
            self.assertEqual(saved['results']['synthetic']['assessments'][0]['verdict'], 'PASS')
            self.assertEqual(len(calls), 1)
