"""Application construction and public payloads survive package relocation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch, sentinel

import hw3
from fisher_agent.company_analyzer import CompanyAnalyzer
from test_company_analyzer import company_tools
from test_returns_disclosure import Model, Tool, TEXT, proposal
from test_returns_evidence import baseline_rows
from test_sales_specialist import ScriptedModel, decision


class BootstrapTests(unittest.TestCase):
    def test_lecturer_factory_delegates_to_the_composition_root(self):
        with patch('fisher_agent.bootstrap.build_agent', return_value=sentinel.agent) as build:
            self.assertIs(hw3.build_agent(), sentinel.agent)
        build.assert_called_once_with(hw3.MODEL_NAME)

    def test_model_construction_preserves_both_specialist_settings_and_shared_tracing(self):
        from fisher_agent.bootstrap import build_agent

        with patch('langchain_deepseek.ChatDeepSeek', return_value=Mock()) as model, \
                patch('fisher_agent.bootstrap.current_tracing', return_value=sentinel.tracing), \
                patch('fisher_agent.bootstrap.CompanyAnalyzer', return_value=sentinel.agent) as analyzer, \
                patch('fisher_agent.bootstrap.MarginRunner') as margin:
            self.assertIs(build_agent(hw3.MODEL_NAME), sentinel.agent)
        self.assertEqual(model.call_count, 2)
        for call in model.call_args_list:
            self.assertEqual(call.kwargs, {
                'model': hw3.MODEL_NAME, 'temperature': 0, 'max_tokens': 600,
                'timeout': 20, 'max_retries': 0, 'extra_body': {'thinking': {'type': 'disabled'}},
            })
        self.assertIs(analyzer.call_args.kwargs['tracing'], sentinel.tracing)
        self.assertIs(margin.call_args.kwargs['tracing'], sentinel.tracing)
        self.assertEqual(margin.call_args.args[0].name, 'industry')

    def test_all_runtime_and_evaluation_modules_import_without_clients_or_credentials(self):
        script = '''
import importlib, os, pkgutil, socket, sys
from unittest.mock import patch
os.environ.clear()
with patch('socket.socket.connect', side_effect=AssertionError('import attempted network')):
    for name in sys.argv[1:]:
        importlib.import_module(name)
    import fisher_agent, evaluation
    for package in (fisher_agent, evaluation):
        for module in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
            importlib.import_module(module.name)
    assert 'langchain_deepseek' not in sys.modules, 'provider imported before construction'
    assert 'langfuse' not in sys.modules, 'optional SDK imported before tracing'
'''
        for order in (('hw3', 'fisher_agent.bootstrap'), ('fisher_agent.bootstrap', 'hw3')):
            result = subprocess.run([sys.executable, '-c', script, *order],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


class BootstrapPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_representative_payloads_match_the_pre_refactor_application(self):
        fixtures = json.loads((Path(__file__).parent / 'fixtures/public_results_before_package_refactor.json').read_text())
        for case, expected in fixtures['cases'].items():
            with self.subTest(case=case):
                rows = baseline_rows()
                proposals = []
                if case in ('acknowledged', 'not_acknowledged', 'uncertain'):
                    rows[4] = ('2025Q3', 3, 3, 3, 1000, 20)
                    classification = {'acknowledged': 'ACKNOWLEDGED',
                                      'not_acknowledged': 'NOT_ACKNOWLEDGED', 'uncertain': 'UNCERTAIN'}[case]
                    proposals = [proposal(classification=classification,
                        quotation='Returns rose sharply this quarter.' if case == 'acknowledged' else None,
                        speaker='Olivia Chen (Chief Financial Officer)' if case == 'acknowledged' else None)]
                sales = ScriptedModel(responses=[RuntimeError('synthetic provider error')
                    if case == 'operational_error' else decision()])
                returns = Model(proposals)
                tools = company_tools(rows) + [
                    Tool('list_documents', 'earnings_call_2025q3.md: Example (Date: 2025-10-29)'),
                    Tool('read_document', TEXT),
                ]
                with patch.dict(os.environ, {}, clear=True), \
                        patch('fisher_agent.bootstrap.current_tracing', return_value=None), \
                        patch('langchain_deepseek.ChatDeepSeek', side_effect=[sales, returns]):
                    agent = hw3.build_agent()
                    self.assertIsInstance(agent, CompanyAnalyzer)
                    result = (await hw3.analyze_companies(agent, {'sample': tools}))['sample']
                self.assertEqual(json.loads(json.dumps(result)), expected)
                if case in ('no_anomaly', 'operational_error'):
                    self.assertEqual(returns.calls, 0)
                    self.assertEqual([t.calls for t in tools[-2:]], [0, 0])
