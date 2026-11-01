import asyncio
import threading
import unittest

from fisher_agent.point5.margin_runner import MarginRunner
from test_industry_margin_strategy import FakeSQL, annual


class MarginRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_and_sql_error_preserve_the_strategy_contract(self):
        runner = MarginRunner()
        good = FakeSQL(annual((2025, 1000, 800)),
                       'industry | operating_margin_pct\nmedical | 20')
        result = await runner.assess('arbitrary', good)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(len(result.evidence), 2)
        self.assertEqual(result.margins[0].revenue, 1000)
        broken = await runner.assess('other', FakeSQL('SQL error: unavailable'))
        self.assertIsNone(broken.verdict)
        self.assertEqual(broken.error.code, 'sql_error')

    async def test_cancellation_propagates_and_does_not_start_another_sql_call(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        class BlockingSQL:
            def invoke(self, arguments):
                calls.append(arguments)
                entered.set()
                release.wait()
                return annual((2025, 1000, 800))

        task = asyncio.create_task(MarginRunner().assess('sample', BlockingSQL()))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.001)
            self.assertTrue(entered.is_set())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            await asyncio.sleep(0.02)
        self.assertEqual(len(calls), 1)

    async def test_stalled_sql_times_out_without_blocking_or_unbounded_threads(self):
        release = threading.Event()
        entered = []

        class BlockingSQL:
            def invoke(self, arguments):
                entered.append(arguments)
                release.wait()
                return 'SQL error: released'

        runner = MarginRunner(timeout_seconds=0.05)
        try:
            tasks = [runner.assess(str(i), BlockingSQL()) for i in range(5)]
            results = await asyncio.wait_for(asyncio.gather(*tasks), 1)
            self.assertLessEqual(len(entered), 2)
            self.assertTrue(all(r.status == 'error' and r.verdict is None for r in results))
            self.assertTrue(all(r.error.code == 'deadline' for r in results))
        finally:
            release.set()
            await asyncio.sleep(0.02)
