import asyncio
import unittest

from fisher_agent.company_analyzer import CompanyAnalyzer
from fisher_agent.evidence_interpreter import EvidenceInterpreter
from fisher_agent.sales_specialist import SalesSpecialist
from test_industry_margin_strategy import FakeSQL, annual
from test_sales_specialist import ScriptedModel, decision, interviews


def company_tools():
    tools, _ = interviews()
    return tools + [FakeSQL(annual((2025, 1000, 800)),
                            'industry | operating_margin_pct\nmedical | 20')]


class CompanyAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_deadline_returns_queued_entries_and_preserves_finished_points(self):
        class SlowSales:
            async def assess(self, name, tools):
                await asyncio.sleep(10)

        analyzer = CompanyAnalyzer(SlowSales(), batch_deadline_seconds=0.05)
        results = await asyncio.wait_for(analyzer.assess_companies(
            {str(i): company_tools() for i in range(5)}), 1)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.points[4].verdict is None for r in results.values()))
        self.assertEqual(results['0'].points[5].verdict, 'PASS')
        self.assertEqual(results['4'].points[5].diagnostics[0].code, 'batch_deadline')

    async def test_company_deadline_preserves_the_completed_independent_point(self):
        class SlowSales:
            async def assess(self, name, tools):
                await asyncio.sleep(10)

        analyzer = CompanyAnalyzer(SlowSales(), deadline_seconds=0.05)
        result = (await analyzer.assess_companies({'sample': company_tools()}))['sample']
        self.assertIsNone(result.points[4].verdict)
        self.assertEqual(result.points[4].diagnostics[0].code, 'deadline')
        self.assertEqual(result.points[5].verdict, 'PASS')
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

        results = await CompanyAnalyzer(BrokenSales()).assess_companies(
            {str(i): company_tools() for i in range(5)})
        self.assertEqual(set(results), {str(i) for i in range(5)})
        self.assertLessEqual(peak, 2)
        for result in results.values():
            self.assertEqual(result.points[5].verdict, 'PASS')
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

        task = asyncio.create_task(CompanyAnalyzer(SlowSales()).assess_companies(
            {'sample': company_tools()}))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cancelled.is_set())

    async def test_combined_path_retains_both_supported_results_and_point14_pending(self):
        model = ScriptedModel(responses=[decision()])
        analyzer = CompanyAnalyzer(SalesSpecialist(EvidenceInterpreter(model)))
        result = (await analyzer.assess_companies({'sample': company_tools()}))['sample']
        self.assertEqual(result.points[4].verdict, 'PASS')
        self.assertEqual(result.points[5].verdict, 'PASS')
        self.assertEqual(result.sales.model_calls, 1)
        self.assertEqual(len(result.margin.evidence), 2)
        public = result.public_result()
        self.assertEqual(public['points'], {4: 'PASS', 5: 'PASS'})
        self.assertIn('Point 14 pending', public['summary'])
