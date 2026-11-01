"""Point 7 behaviour at the specialist boundary, with fake external services."""
import unittest
import asyncio
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from pydantic import Field

from fisher_agent.labour_specialist import LabourSpecialist


GOOD = 'Staff stay for years because pay is fair, supervisors listen and grievances are resolved.'
BAD = 'Supervisors ignore safety complaints, staff leave constantly and grievances go unanswered.'
UNCLEAR = 'I have only just joined and cannot comment on working conditions.'


def decision(verdict='PASS', quote=GOOD, source='current_employee:working_conditions'):
    return dict(verdict=verdict, evidence=quote, evidence_id=source,
                reasoning='The employee describes how management treats staff.')


class LabourModel(BaseChatModel):
    responses: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return 'offline-labour'

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        message = response if isinstance(response, AIMessage) else AIMessage(
            content='', tool_calls=[dict(name='LabourAssessment', args=response, id='assessment')],
            usage_metadata=dict(input_tokens=20, output_tokens=10, total_tokens=30))
        return ChatResult(generations=[ChatGeneration(message=message)])


def interviews(current=GOOD, former=GOOD):
    calls = []

    @tool
    def interview(role: str, topic: str) -> str:
        """Return a synthetic answer owned by this company."""
        calls.append(dict(role=role, topic=topic))
        answer = current if role == 'current_employee' else former
        if isinstance(answer, Exception):
            raise answer
        return answer

    return [interview], calls


class LabourSpecialistTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_deadline_retains_inflight_usage_and_returns_queued_companies(self):
        class SlowModel(LabourModel):
            async def _agenerate(self, *args, **kwargs):
                await asyncio.sleep(1)

        tools, _ = interviews()
        with patch('fisher_agent.labour_specialist.BATCH_DEADLINE_SECONDS', .02):
            results = await LabourSpecialist(SlowModel()).assess_companies(
                {'active': tools, 'queued': tools}, concurrency=1)
        self.assertEqual(set(results), {'active', 'queued'})
        self.assertEqual(results['active'].model_calls, 1)
        self.assertEqual(results['active'].interviews_used, 1)
        self.assertEqual(results['queued'].model_calls, 0)
        self.assertTrue(all(r.point_result.status == 'error' for r in results.values()))

    async def test_concurrent_company_evidence_and_quotes_cannot_cross(self):
        class EchoModel(LabourModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                import json
                evidence = json.loads(messages[1].content)[0]
                response = decision('PASS', evidence['answer'], evidence['evidence_id'])
                return ChatResult(generations=[ChatGeneration(message=AIMessage(
                    content='', tool_calls=[dict(name='LabourAssessment', args=response, id='assessment')]))])

        alpha, _ = interviews(current='Alpha staff are respected and listened to.')
        beta, _ = interviews(current='Beta staff receive fair pay and helpful supervision.')
        model = EchoModel()
        results = await LabourSpecialist(model).assess_companies({'alpha': alpha, 'beta': beta})
        for name, other in [('alpha', 'Beta'), ('beta', 'Alpha')]:
            run = results[name]
            self.assertEqual(run.point_result.verdict, 'PASS')
            self.assertEqual({e.company_id for e in run.evidence}, {name})
            self.assertNotIn(other, run.point_result.summary)

    async def test_model_and_tool_timeouts_preserve_operational_status(self):
        class SlowModel(LabourModel):
            async def _agenerate(self, *args, **kwargs):
                await asyncio.sleep(1)

        tools, _ = interviews()
        with patch('fisher_agent.labour_specialist.MODEL_TIMEOUT_SECONDS', .01):
            run = await LabourSpecialist(SlowModel()).assess('slow-model', tools)
        self.assertEqual(run.point_result.diagnostics[-1].code, 'api_error')
        self.assertEqual(run.model_calls, 1)

        @tool
        async def interview(role: str, topic: str) -> str:
            """Simulate an unresponsive external interview service."""
            await asyncio.sleep(1)
            return GOOD

        with patch('fisher_agent.labour_specialist.TOOL_TIMEOUT_SECONDS', .01):
            run = await LabourSpecialist(LabourModel()).assess('slow-tool', [interview])
        self.assertEqual(run.point_result.diagnostics[-1].code, 'retrieval_error')
        self.assertEqual((run.model_calls, run.interviews_used), (0, 1))

    async def test_company_deadline_and_cancellation(self):
        class SlowModel(LabourModel):
            async def _agenerate(self, *args, **kwargs):
                await asyncio.sleep(1)

        tools, _ = interviews()
        with patch('fisher_agent.labour_specialist.COMPANY_DEADLINE_SECONDS', .01):
            run = await LabourSpecialist(SlowModel()).assess('deadline', tools)
        self.assertEqual((run.point_result.status, run.point_result.verdict), ('error', None))
        self.assertEqual(run.point_result.diagnostics[-1].code, 'deadline')
        task = asyncio.create_task(LabourSpecialist(SlowModel()).assess('cancel', tools))
        await asyncio.sleep(.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_company_concurrency_is_bounded_and_invalid_values_rejected(self):
        active, peak = 0, 0

        @tool
        async def interview(role: str, topic: str) -> str:
            """Exercise actual company scheduling."""
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(.01)
            active -= 1
            return GOOD

        specialist = LabourSpecialist(LabourModel(responses=[decision()] * 4))
        results = await specialist.assess_companies({str(i): [interview] for i in range(4)})
        self.assertEqual(peak, 2)
        self.assertTrue(all(r.point_result.status == 'complete' for r in results.values()))
        for concurrency in (0, 3):
            with self.assertRaises(ValueError):
                await specialist.assess_companies({}, concurrency=concurrency)

    async def test_invalid_schema_quotes_and_sources_are_errors_without_second_interview(self):
        invalid = [decision(quote='Everyone is happy.'), decision(quote=GOOD.lower()),
                   decision(source='former_employee:working_conditions'),
                   decision(source='other_company:current_employee:working_conditions'),
                   decision(verdict='UNKNOWN'), {**decision(), 'reasoning': '  '},
                   {**decision(), 'extra': 'unexpected'}, {'verdict': 'PASS'},
                   AIMessage(content='not a structured response'),
                   AIMessage(content='', tool_calls=[
                       dict(name='LabourAssessment', args=decision(), id='one'),
                       dict(name='LabourAssessment', args=decision(), id='two')])]
        for response in invalid:
            with self.subTest(response=response):
                tools, calls = interviews()
                run = await LabourSpecialist(LabourModel(responses=[response] * 2)).assess('bad', tools)
                self.assertEqual((run.point_result.status, run.point_result.verdict), ('error', None))
                self.assertEqual(run.point_result.diagnostics[-1].code, 'invalid_output')
                self.assertEqual((len(calls), run.model_calls), (1, 2))
                self.assertEqual(run.assessments, [])

    async def test_invalid_output_can_be_repaired_once_using_the_same_interview(self):
        model = LabourModel(responses=[AIMessage(content='bad'), decision()])
        tools, calls = interviews()
        run = await LabourSpecialist(model).assess('repair', tools)
        self.assertEqual(run.point_result.verdict, 'PASS')
        self.assertEqual((len(calls), run.model_calls), (1, 2))
        self.assertEqual(run.point_result.diagnostics[0].code, 'invalid_output')

    async def test_interview_budget_exhaustion_and_retrieval_errors_never_reach_model(self):
        for answer in [ConnectionError('secret'), '', ' ', None,
                       'Interview limit reached: 10 interviews per company.',
                       "Unknown role 'current_employee'.", "Unknown topic 'working_conditions'."]:
            with self.subTest(answer=answer):
                tools, calls = interviews(current=answer)
                run = await LabourSpecialist(LabourModel()).assess('broken', tools)
                self.assertEqual((run.point_result.status, run.point_result.verdict), ('error', None))
                self.assertEqual(run.point_result.diagnostics[-1].code, 'retrieval_error')
                self.assertEqual((len(calls), run.model_calls), (1, 0))
                self.assertEqual(run.evidence, [])
                self.assertNotIn('secret', repr(run))

    async def test_api_failure_isolated_from_the_next_company(self):
        model = LabourModel(responses=[ConnectionError('private header'), decision()])
        broken, _ = interviews()
        healthy, _ = interviews()
        results = await LabourSpecialist(model).assess_companies(
            {'broken': broken, 'healthy': healthy}, concurrency=1)
        self.assertEqual(set(results), {'broken', 'healthy'})
        self.assertEqual(results['broken'].point_result.verdict, None)
        self.assertEqual(results['broken'].point_result.diagnostics[-1].code, 'api_error')
        self.assertEqual(results['broken'].model_calls, 1)
        self.assertNotIn('private header', repr(results['broken']))
        self.assertEqual(results['healthy'].point_result.verdict, 'PASS')

    async def test_failed_conditional_interview_retains_uncertainty_and_reports_error(self):
        model = LabourModel(responses=[decision('UNCERTAIN', UNCLEAR)])
        tools, calls = interviews(current=UNCLEAR, former=ConnectionError())
        run = await LabourSpecialist(model).assess('partial', tools)
        self.assertEqual((run.point_result.status, run.point_result.verdict), ('error', None))
        self.assertEqual((len(calls), run.model_calls, len(run.evidence)), (2, 1, 1))

    async def test_two_interviews_and_four_model_calls_are_a_hard_bound(self):
        model = LabourModel(responses=[AIMessage(content='bad'), decision('UNCERTAIN', UNCLEAR),
            AIMessage(content='bad'), decision('UNCERTAIN', UNCLEAR)])
        tools, calls = interviews(current=UNCLEAR, former=UNCLEAR)
        run = await LabourSpecialist(model).assess('bounded', tools)
        self.assertEqual((len(calls), run.model_calls), (2, 4))
        self.assertEqual(run.point_result.status, 'insufficient_evidence')

    async def test_missing_or_duplicate_interview_tool_is_an_explicit_error(self):
        tools, _ = interviews()
        for supplied in ([], tools + tools):
            run = await LabourSpecialist(LabourModel()).assess('missing', supplied)
            self.assertEqual(run.point_result.status, 'error')
            self.assertEqual(run.interviews_used, 0)

    async def test_clear_fail_is_an_evidence_backed_investment_verdict(self):
        tools, calls = interviews(current=BAD)
        run = await LabourSpecialist(LabourModel(responses=[decision('FAIL', BAD)])).assess('poor', tools)
        self.assertEqual((run.point_result.status, run.point_result.verdict), ('complete', 'FAIL'))
        self.assertIn(BAD, run.point_result.summary)
        self.assertEqual(len(calls), 1)

    async def test_uncertainty_uses_former_employee_once_and_reassesses_both(self):
        model = LabourModel(responses=[decision('UNCERTAIN', UNCLEAR),
            decision('PASS', GOOD, 'former_employee:working_conditions')])
        tools, calls = interviews(current=UNCLEAR)
        run = await LabourSpecialist(model).assess('unclear', tools)
        self.assertEqual((run.point_result.status, run.point_result.verdict), ('complete', 'PASS'))
        self.assertEqual(calls, [dict(role='current_employee', topic='working_conditions'),
                                dict(role='former_employee', topic='working_conditions')])
        self.assertEqual(run.model_calls, 2)
        self.assertIn(UNCLEAR, model.seen[1][1].content)
        self.assertIn(GOOD, model.seen[1][1].content)

    async def test_repeated_uncertainty_remains_unresolved_with_no_forced_fail(self):
        model = LabourModel(responses=[decision('UNCERTAIN', UNCLEAR)] * 2)
        tools, calls = interviews(current=UNCLEAR, former=UNCLEAR)
        run = await LabourSpecialist(model).assess('uninformative', tools)
        self.assertEqual((run.point_result.status, run.point_result.verdict),
                         ('insufficient_evidence', None))
        self.assertEqual((len(calls), run.model_calls), (2, 2))

    async def test_clear_pass_is_grounded_in_current_employee_and_maps_to_point_result(self):
        model = LabourModel(responses=[decision()])
        tools, calls = interviews()
        run = await LabourSpecialist(model).assess('synthetic', tools)
        result = run.point_result
        self.assertEqual((result.company_id, result.point, result.status, result.verdict),
                         ('synthetic', 7, 'complete', 'PASS'))
        self.assertIn(GOOD, result.summary)
        self.assertEqual(result.provenance[0].company_id, 'synthetic')
        self.assertEqual(result.provenance[0].source_tool, 'interview')
        self.assertEqual(result.provenance[0].evidence_id, 'current_employee:working_conditions')
        self.assertEqual(calls, [dict(role='current_employee', topic='working_conditions')])
        self.assertEqual((run.interviews_used, run.model_calls), (1, 1))
        self.assertEqual(run.usage['total_tokens'], 30)


if __name__ == '__main__':
    unittest.main()
