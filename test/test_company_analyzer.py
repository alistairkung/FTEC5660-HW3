import asyncio
from contextlib import contextmanager
import unittest
from unittest.mock import patch

from fisher_agent.company_analyzer import CompanyAnalyzer
from fisher_agent.contracts import Diagnostic, PointResult, ProvenanceReference
from fisher_agent.evidence_interpreter import EvidenceInterpreter
from fisher_agent.margin_runner import MarginRunner
from fisher_agent.returns_disclosure import Point14ReturnsStrategy
from fisher_agent.returns_disclosure.records import ReturnsRun
from fisher_agent.sales_specialist import SalesSpecialist
from test_industry_margin_strategy import FakeSQL, annual
from test_returns_evidence import baseline_rows, raw_rows
from test_sales_specialist import ScriptedModel, decision, interviews


def company_tools(returns_rows=None):
    class CompanySQL(FakeSQL):
        async def ainvoke(self, arguments, config=None):
            self.queries.append(arguments['query'])
            return raw_rows(returns_rows if returns_rows is not None else baseline_rows())

    tools, _ = interviews()
    return tools + [CompanySQL(annual((2025, 1000, 800)),
                               'industry | operating_margin_pct\nmedical | 20')]


class ScriptedReturns:
    def __init__(self, verdict='PASS', status='complete', *, error=None, company_id=None,
                 point=14, diagnostics=()):
        self.verdict, self.status, self.error = verdict, status, error
        self.company_id, self.point, self.diagnostics = company_id, point, diagnostics
        self.seen = []

    async def assess(self, company_id, tools):
        self.seen.append((company_id, tools))
        if self.error:
            raise self.error
        company_id = self.company_id or company_id
        source = ProvenanceReference(company_id + ':returns', company_id, 'sql_query')
        result = PointResult(company_id, self.point, self.verdict, self.status,
                             'Same-quarter returns disclosure assessed.', (source,), self.diagnostics)
        return ReturnsRun(result, diagnostics=list(self.diagnostics), model_calls=1,
                          usage={'input_tokens': 11, 'output_tokens': 7, 'total_tokens': 18},
                          tool_calls={'sql_query': 1, 'list_documents': 1, 'read_document': 1})

    async def assess_companies(self, companies):
        raise AssertionError('The parent must reuse the per-company assess path')


class CompanyAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_deadline_returns_queued_entries_and_preserves_finished_points(self):
        class SlowSales:
            async def assess(self, name, tools):
                await asyncio.sleep(10)

        analyzer = CompanyAnalyzer(SlowSales(), returns_strategy=Point14ReturnsStrategy(),
                                   batch_deadline_seconds=0.05)
        results = await asyncio.wait_for(analyzer.assess_companies(
            {str(i): company_tools() for i in range(5)}), 1)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.points[4].verdict is None for r in results.values()))
        self.assertEqual(results['0'].points[5].verdict, 'PASS')
        self.assertEqual(results['4'].points[5].diagnostics[0].code, 'batch_deadline')
        self.assertEqual(results['0'].points[14].verdict, 'PASS')
        self.assertEqual(results['4'].points[14].diagnostics[0].code, 'batch_deadline')
        self.assertTrue(all(set(r.public_result()['points']) == {4, 5, 14} for r in results.values()))

    async def test_company_deadline_preserves_the_completed_independent_point(self):
        class SlowSales:
            async def assess(self, name, tools):
                await asyncio.sleep(10)

        analyzer = CompanyAnalyzer(SlowSales(), returns_strategy=Point14ReturnsStrategy(), deadline_seconds=0.05)
        result = (await analyzer.assess_companies({'sample': company_tools()}))['sample']
        self.assertIsNone(result.points[4].verdict)
        self.assertEqual(result.points[4].diagnostics[0].code, 'deadline')
        self.assertEqual(result.points[5].verdict, 'PASS')
        self.assertEqual(result.points[14].verdict, 'PASS')
        self.assertEqual(result.public_result()['points'][4], 'FAIL')
        self.assertIn('operational FAIL fallback', result.public_result()['summary'])

    async def test_exception_isolation_and_company_concurrency(self):
        active, peak = 0, 0

        class BrokenSales:
            async def assess(self, name, tools):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(0.01)
                    raise RuntimeError('sensitive provider message')
                finally:
                    active -= 1

        results = await CompanyAnalyzer(BrokenSales(), returns_strategy=Point14ReturnsStrategy()).assess_companies(
            {str(i): company_tools() for i in range(5)})
        self.assertEqual(set(results), {str(i) for i in range(5)})
        self.assertLessEqual(peak, 2)
        for result in results.values():
            self.assertEqual(result.points[5].verdict, 'PASS')
            self.assertEqual(result.points[14].verdict, 'PASS')
            self.assertIsNone(result.points[4].verdict)
            self.assertNotIn('sensitive', str(result))

    async def test_batch_cancellation_propagates(self):
        cancelled = asyncio.Event()

        class SlowSales:
            async def assess(self, name, tools):
                try:
                    await asyncio.sleep(10)
                finally:
                    cancelled.set()

        task = asyncio.create_task(CompanyAnalyzer(SlowSales(), returns_strategy=Point14ReturnsStrategy()).assess_companies(
            {'sample': company_tools()}))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cancelled.is_set())

    async def test_combined_path_retains_three_supported_results_and_raw_returns(self):
        model = ScriptedModel(responses=[decision()])
        tools = company_tools()
        analyzer = CompanyAnalyzer(SalesSpecialist(EvidenceInterpreter(model)),
                                   returns_strategy=Point14ReturnsStrategy())
        with patch('observability.tracing._load_backend', side_effect=AssertionError('tracing disabled')) as backend:
            result = (await analyzer.assess_companies({'sample': tools}))['sample']
        backend.assert_not_called()
        self.assertEqual(result.points[4].verdict, 'PASS')
        self.assertEqual(result.points[5].verdict, 'PASS')
        self.assertEqual(result.sales.model_calls, 1)
        self.assertEqual(len(result.margin.evidence), 2)
        self.assertEqual(result.points[14].verdict, 'PASS')
        self.assertIs(result.points[14], result.returns_run.point_result)
        self.assertEqual(result.returns_run.model_calls, 0)
        self.assertEqual(result.returns_run.tool_calls, {'sql_query': 1})
        self.assertTrue(all(p.company_id == 'sample' for p in result.points.values()))
        public = result.public_result()
        self.assertEqual(public['points'], {4: 'PASS', 5: 'PASS', 14: 'PASS'})
        self.assertNotIn('pending', public['summary'])

    async def test_returns_failure_and_uncertainty_preserve_other_points(self):
        for strategy in (ScriptedReturns(error=RuntimeError('sensitive provider message')),
                         ScriptedReturns(None, 'insufficient_evidence')):
            with self.subTest(status=strategy.status):
                analyzer = CompanyAnalyzer(SalesSpecialist(EvidenceInterpreter(ScriptedModel(responses=[decision()]))),
                                           returns_strategy=strategy)
                result = (await analyzer.assess_companies({'sample': company_tools()}))['sample']
                self.assertEqual(result.points[4].verdict, 'PASS')
                self.assertEqual(result.points[5].verdict, 'PASS')
                self.assertIsNone(result.points[14].verdict)
                self.assertEqual(result.public_result()['points'][14], 'FAIL')
                self.assertIn('fallback', result.public_result()['summary'])
                if strategy.status == 'insufficient_evidence':
                    self.assertIn('insufficient-evidence FAIL fallback', result.public_result()['summary'])
                self.assertNotIn('sensitive', str(result))
                self.assertEqual(len(strategy.seen), 1)

    async def test_margin_failure_preserves_sales_and_returns(self):
        tools = company_tools()
        tools[-1].responses = iter(['SQL error: unavailable'])
        analyzer = CompanyAnalyzer(SalesSpecialist(EvidenceInterpreter(ScriptedModel(responses=[decision()]))),
                                   returns_strategy=Point14ReturnsStrategy())
        result = (await analyzer.assess_companies({'sample': tools}))['sample']
        self.assertIsNone(result.points[5].verdict)
        self.assertEqual(result.points[4].verdict, 'PASS')
        self.assertEqual(result.points[14].verdict, 'PASS')
        self.assertEqual(result.public_result()['points'], {4: 'PASS', 5: 'FAIL', 14: 'PASS'})
        self.assertEqual(result.points[5].diagnostics[0].code, 'sql_error')

    async def test_real_returns_acknowledgement_paths_use_each_companys_own_tools(self):
        from test_returns_disclosure import Model, Tool, TEXT, proposal

        rows = baseline_rows()
        rows[4] = ('2025Q3', 3, 3, 3, 1000, 20)
        companies = {}
        for name, acknowledged in (('left', True), ('right', False)):
            tools = company_tools(rows)
            text = (TEXT if acknowledged else TEXT.replace(
                'Returns rose sharply this quarter. We are replacing affected units.',
                'Product quality remained excellent and returns were negligible.'))
            tools += [Tool('list_documents', 'earnings_call_2025q3.md: Example (Date: 2025-10-29)'),
                      Tool('read_document', text)]
            companies[name] = tools
        model = Model([proposal(), proposal(classification='NOT_ACKNOWLEDGED', quotation=None, speaker=None)])
        analyzer = CompanyAnalyzer(
            SalesSpecialist(EvidenceInterpreter(ScriptedModel(responses=[decision(), decision()]))),
            returns_strategy=Point14ReturnsStrategy(model))
        results = await analyzer.assess_companies(companies)
        self.assertEqual(results['left'].public_result()['points'], {4: 'PASS', 5: 'PASS', 14: 'PASS'})
        self.assertEqual(results['right'].public_result()['points'], {4: 'PASS', 5: 'PASS', 14: 'FAIL'})
        self.assertEqual(model.calls, 2)
        for name, result in results.items():
            self.assertEqual(len(companies[name][1].queries), 3)
            self.assertEqual([tool.calls for tool in companies[name][-2:]], [1, 1])
            self.assertEqual(result.sales.interviews_used, 1)
            self.assertEqual(result.returns_run.model_calls, 1)
            self.assertEqual(result.returns_run.usage['total_tokens'], 15)
            self.assertTrue(all(source.company_id == name for source in result.returns_run.evidence))
            self.assertTrue(all(source.company_id == name for source in result.points[14].provenance))
            self.assertTrue(all(item.company_id == name for item in result.returns_run.comparisons))

    async def test_returns_deadline_preserves_completed_sales_and_margin(self):
        class SlowReturns:
            async def assess(self, name, tools):
                await asyncio.sleep(10)

        analyzer = CompanyAnalyzer(SalesSpecialist(EvidenceInterpreter(ScriptedModel(responses=[decision()]))),
                                   returns_strategy=SlowReturns(), deadline_seconds=0.05)
        result = (await analyzer.assess_companies({'sample': company_tools()}))['sample']
        self.assertEqual(result.points[4].verdict, 'PASS')
        self.assertEqual(result.points[5].verdict, 'PASS')
        self.assertIsNone(result.points[14].verdict)
        self.assertEqual(result.points[14].diagnostics[0].code, 'deadline')

    async def test_supported_returns_fail_and_diagnostics_are_retained_in_company_trace(self):
        recorded = []

        class Tracing:
            @contextmanager
            def observation(self, name, **kwargs):
                class Span:
                    trace_id = 'company-trace'

                    def update(self, **kwargs):
                        recorded.append((name, kwargs))
                yield Span()

        diagnostic = Diagnostic('2025Q4', 'disclosure_uncertain')
        strategy = ScriptedReturns('FAIL', diagnostics=(diagnostic,))
        analyzer = CompanyAnalyzer(SalesSpecialist(EvidenceInterpreter(ScriptedModel(responses=[decision()]))),
                                   returns_strategy=strategy, margin=MarginRunner(), tracing=Tracing())
        result = (await analyzer.assess_companies({'sample': company_tools()}))['sample']
        self.assertEqual(result.public_result()['points'], {4: 'PASS', 5: 'PASS', 14: 'FAIL'})
        self.assertEqual(result.returns_run.diagnostics, [diagnostic])
        self.assertEqual(result.returns_run.usage['total_tokens'], 18)
        output = next(payload['output'] for name, payload in recorded if name == 'assess-company')
        self.assertEqual(output['point_statuses'], {4: 'complete', 5: 'complete', 14: 'complete'})
        self.assertEqual(output['point14']['model_calls'], 1)
        self.assertEqual(output['point14']['usage']['total_tokens'], 18)
        self.assertEqual(output['point14']['diagnostics'][0]['code'], 'disclosure_uncertain')
        self.assertEqual(output['model_calls'], 2)
        self.assertEqual(output['usage']['total_tokens'], 48)
        self.assertTrue(output['usage_complete'])

    async def test_rejects_cross_company_and_wrong_point_returns_results(self):
        for strategy in (ScriptedReturns(company_id='other'), ScriptedReturns(point=4),
                         ScriptedReturns(None, 'pending')):
            analyzer = CompanyAnalyzer(SalesSpecialist(EvidenceInterpreter(ScriptedModel(responses=[decision()]))),
                                       returns_strategy=strategy)
            result = (await analyzer.assess_companies({'sample': company_tools()}))['sample']
            self.assertIsNone(result.points[14].verdict)
            self.assertEqual(result.points[14].status, 'error')
            self.assertEqual(set(result.public_result()['points']), {4, 5, 14})
