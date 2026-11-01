"""Evaluation opt-in, artifact integrity and post-prediction label isolation."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from evaluation.returns_disclosure import main, score_runs
from fisher_agent.contracts import PointResult, ProvenanceReference
from fisher_agent.point14 import Point14ReturnsStrategy
from fisher_agent.point14.records import ReturnsRun
import test_returns_disclosure as fixtures
from test_returns_evidence import raw_rows,baseline_rows


class ReturnsEvaluationTests(unittest.TestCase):
    def test_financial_only_has_no_model_documents_or_label_reads_and_no_overwrite(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'example').mkdir();output=folder/'report.json'
            sql=fixtures.Tool('sql_query',raw_rows(baseline_rows()))
            args=['evaluate','--financial-only','--data-folder',str(folder),'--output',str(output)]
            with patch.object(sys,'argv',args),patch('hw3.make_tools',return_value=[sql]), \
                    patch('hw3.read_ground_truth',side_effect=AssertionError('must not load labels')), \
                    patch('evaluation.returns_disclosure.build_returns_strategy',side_effect=AssertionError('no model')):
                self.assertEqual(main(),0)
            report=json.loads(output.read_text())
            self.assertEqual(report['summary']['model_calls'],0)
            self.assertIsNone(report['scores'])
            before=output.read_bytes()
            with patch.object(sys,'argv',args),self.assertRaises(SystemExit):main()
            self.assertEqual(output.read_bytes(),before)

    def test_live_labels_are_loaded_only_after_predictions_and_tools_are_not_repeated(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'example').mkdir();output=folder/'live.json'
            tools=fixtures.ReturnsStrategyTests().tools();model=fixtures.Model([fixtures.proposal()])
            def labels(_):
                self.assertEqual(model.calls,1)
                self.assertEqual([t.calls for t in tools],[1,1,1])
                return {'example':{'points':{'14':'PASS'}}}
            args=['evaluate','--live','--data-folder',str(folder),'--output',str(output),'--companies','example']
            with patch.object(sys,'argv',args),patch('hw3.make_tools',return_value=tools), \
                    patch('hw3.load_env_file'),patch('hw3.read_ground_truth',side_effect=labels), \
                    patch('evaluation.returns_disclosure.build_returns_strategy',return_value=Point14ReturnsStrategy(model)):
                self.assertEqual(main(),0)
            self.assertEqual(json.loads(output.read_text())['scores']['grounded_correct'],1)

    def test_none_is_wrong_without_becoming_a_grounded_fail(self):
        source=(ProvenanceReference('sql','negative','sql_query'),)
        runs={'negative':ReturnsRun(PointResult('negative',14,'FAIL','complete','Verified negative',source)),
              'positive':ReturnsRun(PointResult('positive',14,None,'insufficient_evidence','Unknown')),
              'error':ReturnsRun(PointResult('error',14,None,'error','API failure'),failure_status='error')}
        score=score_runs(runs,{'negative':'FAIL','positive':'PASS','error':'FAIL'})
        self.assertEqual(score['grounded_correct'],1)
        self.assertEqual(score['hypothetical_fail_fallback_credit'],1)
        self.assertEqual(score['operational_failures'],['error'])
        self.assertEqual(score['semantic_abstentions'],['positive'])
        self.assertEqual(score['balanced_accuracy'],0.25)
