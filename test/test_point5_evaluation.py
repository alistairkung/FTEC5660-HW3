import ast
from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.compare_point5 import compare, evaluate_strategies, main
from fisher_agent.historical_margin_strategy import HistoricalMarginStrategy
from fisher_agent.industry_margin_strategy import IndustryMarginStrategy
from test_industry_margin_strategy import FakeSQL, annual


class Point5EvaluationTests(unittest.TestCase):
    def test_optional_spans_record_strategy_evidence_without_answers(self):
        recorded = []

        class FakeTracing:
            @contextmanager
            def observation(self, name, **metadata):
                class Span:
                    def update(self, **payload):
                        recorded.append((name, metadata, payload))
                yield Span()

        tool = FakeSQL(annual((2025, 1000, 800)),
                       'industry | operating_margin_pct\nmedical | 20',
                       annual((2023, 1000, 800), (2024, 1000, 800), (2025, 1000, 800)))
        evaluate_strategies({'id': tool}, [IndustryMarginStrategy(), HistoricalMarginStrategy()],
                            tracing=FakeTracing())
        self.assertEqual([span[0] for span in recorded], ['point5-industry', 'point5-historical'])
        for _, metadata, payload in recorded:
            self.assertEqual(metadata['company_id'], 'id')
            self.assertEqual(metadata['fisher_point'], 5)
            self.assertTrue(payload['output']['evidence'])
            self.assertNotIn('labels', payload['output'])
            self.assertNotIn('ground_truth', json.dumps(payload))

    def test_runtime_package_has_no_label_or_evaluation_dependencies(self):
        runtime = Path(__file__).resolve().parents[1] / 'fisher_agent'
        margin_modules = {'margin_records.py', 'evidence_retriever.py', 'point_rules.py',
                          'historical_margin_strategy.py', 'industry_margin_strategy.py'}
        self.assertTrue(all((runtime / name).is_file() for name in margin_modules))
        for path in runtime.glob('*.py'):
            forbidden = {'evaluation', 'sqlite3'}
            # Other specialists construct permitted models; Point 5 stays deterministic.
            if path.name in margin_modules:
                forbidden |= {'hw3', 'langchain_deepseek'}
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = ([node.module] if isinstance(node, ast.ImportFrom) else
                         [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                self.assertFalse({name.split('.')[0] for name in names if name} & forbidden, path)
            self.assertNotIn('ground_truth', path.read_text(), path)

    def test_cli_reads_answers_only_after_both_strategies_finish(self):
        tool = FakeSQL(annual((2025, 1000, 800)),
                       'industry | operating_margin_pct\nmedical | 20',
                       annual((2023, 1000, 800), (2024, 1000, 800), (2025, 1000, 800)))

        def read_answers(_):
            self.assertEqual(len(tool.queries), 3)
            return {'id': {'points': {'5': 'PASS'}}}

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'results.json'
            with patch('sys.argv', ['compare_point5', '--output', str(output)]), \
                    patch('hw3.company_folders', return_value=[Path('id')]), \
                    patch('hw3.make_tools', return_value=[tool]), \
                    patch('hw3.read_ground_truth', side_effect=read_answers), \
                    patch('evaluation.compare_point5.Tracing', side_effect=AssertionError('unexpected tracing')), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(output.read_text())['report']['metrics']['industry']['completed'], 1)

    def test_scoring_is_separate_from_strategy_execution_and_errors_count_wrong(self):
        tools = {
            'passing': FakeSQL(annual((2025, 1000, 800)),
                               'industry | operating_margin_pct\nmedical | 20'),
            'failing': FakeSQL(annual((2025, 1000, 900)),
                               'industry | operating_margin_pct\nmedical | 20'),
            'broken': FakeSQL('SQL error: unavailable'),
        }
        results = evaluate_strategies(tools, [IndustryMarginStrategy()])
        report = compare(results, {'passing': 'PASS', 'failing': 'FAIL', 'broken': 'FAIL'})
        metrics = report['metrics']['industry']
        self.assertEqual(metrics['pass_recall'], 1)
        self.assertEqual(metrics['fail_recall'], 0.5)
        self.assertEqual(metrics['balanced_accuracy'], 0.75)
        self.assertEqual(metrics['sql_errors'], ['broken'])
        self.assertEqual(metrics['completed'], 2)
        # Flip labels only after execution: evidence and runtime outcomes are unchanged.
        changed = compare(results, {'passing': 'FAIL', 'failing': 'PASS', 'broken': 'PASS'})
        self.assertEqual(changed['metrics']['industry']['balanced_accuracy'], 0)
        self.assertEqual(results['industry']['passing'].verdict, 'PASS')

    def test_comparison_reports_disagreements_with_ground_truth_and_between_strategies(self):
        tool = FakeSQL(annual((2025, 1000, 900)),
                       'industry | operating_margin_pct\nmedical | 20',
                       annual((2023, 1000, 950), (2024, 1000, 920), (2025, 1000, 900)))
        results = evaluate_strategies({'id': tool},
                                      [IndustryMarginStrategy(), HistoricalMarginStrategy()])
        report = compare(results, {'id': 'PASS'})
        self.assertEqual(report['strategy_disagreements'], ['id'])
        self.assertEqual(report['metrics']['industry']['label_disagreements'], ['id'])
        self.assertEqual(report['metrics']['historical']['label_disagreements'], [])
        self.assertIsNone(report['metrics']['industry']['fail_recall'])
        self.assertIsNone(report['metrics']['industry']['balanced_accuracy'])

    def test_unexpected_strategy_failure_is_isolated_per_company_and_strategy(self):
        class BrokenStrategy:
            name = 'broken'

            def evaluate(self, company_id, sql_query):
                raise RuntimeError('unexpected')

        results = evaluate_strategies({'one': FakeSQL(), 'two': FakeSQL()}, [BrokenStrategy()])
        self.assertEqual(set(results['broken']), {'one', 'two'})
        self.assertTrue(all(result.status == 'error' for result in results['broken'].values()))

    def test_scoring_rejects_missing_labels_or_predictions(self):
        result = IndustryMarginStrategy().evaluate('id', FakeSQL('SQL error: unavailable'))
        for predictions, labels in [({'industry': {'id': result}}, {}),
                                    ({'industry': {}}, {'id': 'PASS'}),
                                    ({'industry': {'id': result}}, {'id': 'UNKNOWN'})]:
            with self.subTest(labels=labels):
                with self.assertRaises(ValueError):
                    compare(predictions, labels)
