"""Development scoring uses grounded PointResults; labels never enter predictions."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from evaluation.point7 import evaluate, score_results
from fisher_agent.labour_specialist import LabourSpecialist
from test_labour_specialist import LabourModel, decision, interviews


class Point7EvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_errors_receive_no_credit_even_for_fail_labels(self):
        good, _ = interviews()
        bad, _ = interviews()
        error, _ = interviews(current=ConnectionError())
        specialist = LabourSpecialist(LabourModel(responses=[decision(), decision('FAIL')]))
        results = await specialist.assess_companies({'pass': good, 'fail': bad, 'error': error},
                                                   concurrency=1)
        labels = {n: {'points': {'7': v}} for n, v in [('pass', 'PASS'), ('fail', 'FAIL'), ('error', 'FAIL')]}
        metrics = score_results(results, labels)
        self.assertEqual(metrics['grounded_correct'], 2)
        self.assertEqual(metrics['grounded_accuracy'], 2/3)
        self.assertEqual(metrics['pass_recall'], 1)
        self.assertEqual(metrics['fail_recall'], .5)
        self.assertEqual(metrics['balanced_accuracy'], .75)
        self.assertEqual(metrics['operational_errors'], ['error'])
        with self.assertRaises(ValueError):
            score_results(results, {})

    async def test_report_preserves_provenance_and_loads_labels_after_prediction(self):
        specialist = LabourSpecialist(LabourModel(responses=[decision()]))
        tools, calls = interviews()

        def labels(_):
            self.assertEqual(len(calls), 1)
            return {'synthetic': {'points': {'7': 'PASS'}}}

        with TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'synthetic').mkdir()
            output = folder / 'report.json'
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake',
                                         'LANGFUSE_TRACING_ENABLED': 'false'}), \
                 patch('evaluation.point7.hw3.load_env_file'), \
                 patch('evaluation.point7.hw3.make_tools', return_value=tools), \
                 patch('evaluation.point7.hw3.INTERVIEWS_USED', {'synthetic': 1}), \
                 patch('evaluation.point7.hw3.read_ground_truth', side_effect=labels), \
                 patch('evaluation.point7.build_labour_specialist', return_value=specialist):
                report = await evaluate(folder, output)
            saved = json.loads(output.read_text())
        self.assertTrue(report['live_evaluation_complete'])
        self.assertEqual(saved['metrics']['grounded_correct'], 1)
        self.assertEqual(saved['results']['synthetic']['point_result']['point'], 7)
        self.assertEqual(saved['results']['synthetic']['lecturer_interviews_used'], 1)
        self.assertEqual(saved['results']['synthetic']['assessments'][0]['verdict'], 'PASS')
