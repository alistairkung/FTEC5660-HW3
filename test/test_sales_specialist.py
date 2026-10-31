"""Point 4 behaviour through injected LangChain model and company tools."""
import unittest
import asyncio
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from pydantic import Field

from fisher_agent.evidence_interpreter import EvidenceInterpreter
from fisher_agent.sales_specialist import SalesSpecialist


GOOD = 'Their salespeople understand our process and solve technical problems.'
BAD = 'Their salespeople cannot explain the products and never answer support calls.'


def decision(verdict='PASS', quote=GOOD, evidence_id='customer:sales_team'):
    return dict(verdict=verdict, evidence=quote, evidence_id=evidence_id,
                reasoning='The interview describes the sales team’s ability to support customers.')


class ScriptedModel(BaseChatModel):
    responses: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return 'offline-script'

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        message = response if isinstance(response, AIMessage) else AIMessage(
            content='', tool_calls=[dict(name='SalesAssessment', args=response, id='assessment')],
            usage_metadata=dict(input_tokens=20, output_tokens=10, total_tokens=30))
        return ChatResult(generations=[ChatGeneration(message=message)])


def interviews(customer=GOOD, competitor=GOOD):
    calls = []

    @tool
    def interview(role: str, topic: str) -> str:
        """Return one synthetic, company-scoped interview."""
        calls.append(dict(role=role, topic=topic))
        answer = customer if role == 'customer' else competitor
        if isinstance(answer, Exception):
            raise answer
        return answer

    return [interview], calls


class SalesSpecialistTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_negative_finishes_without_competitor(self):
        model = ScriptedModel(responses=[decision('FAIL', BAD)])
        tools, calls = interviews(customer=BAD)
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('negative', tools)
        self.assertEqual(result.verdict, 'FAIL')
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(model.seen), 1)

    async def test_customer_evidence_produces_grounded_pass_and_stops(self):
        model = ScriptedModel(responses=[decision()])
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('synthetic', tools)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(result.status, 'assessed')
        self.assertEqual(calls, [dict(role='customer', topic='sales_team')])
        self.assertEqual(result.model_calls, 1)
        self.assertEqual(result.interviews_used, 1)
        self.assertEqual(result.assessments[0].evidence, GOOD)
        self.assertEqual(result.evidence[0].company_id, 'synthetic')
        self.assertEqual(result.usage['total_tokens'], 30)

    async def test_uncertainty_retrieves_competitor_and_reassesses_both(self):
        unclear = 'The products are popular; I do not deal with the salespeople.'
        model = ScriptedModel(responses=[decision('UNCERTAIN', unclear),
                                       decision('PASS', GOOD, 'competitor:sales_team')])
        tools, calls = interviews(customer=unclear)
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('ambiguous', tools)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(calls, [dict(role='customer', topic='sales_team'),
                                dict(role='competitor', topic='sales_team')])
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(result.interviews_used, 2)
        self.assertTrue(result.fallback_triggered)
        self.assertIn(unclear, model.seen[1][1].content)
        self.assertIn(GOOD, model.seen[1][1].content)

    async def test_repeated_uncertainty_requires_one_final_adjudication(self):
        model = ScriptedModel(responses=[decision('UNCERTAIN'), decision('UNCERTAIN'), decision()])
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('adjudicated', tools)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(result.status, 'adjudicated')
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.model_calls, 3)
        self.assertTrue(result.adjudication_used)
        self.assertIn('Choose PASS or FAIL', model.seen[2][0].content)

    async def test_malformed_output_retries_same_evidence_without_new_interview(self):
        model = ScriptedModel(responses=[AIMessage(content='not JSON'), decision()])
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('repaired', tools)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.diagnostics[0]['category'], 'invalid_output')

    async def test_invented_quote_cannot_become_success_or_trigger_interview(self):
        model = ScriptedModel(responses=[decision(quote='Sales increased tenfold.')] * 2)
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('ungrounded', tools)
        self.assertEqual(result.verdict, 'FAIL')
        self.assertEqual(result.status, 'invalid_output')
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(result.assessments, [])

    async def test_api_failure_is_explicit_and_other_companies_still_complete(self):
        model = ScriptedModel(responses=[ConnectionError('secret must not leak'), decision()])
        specialist = SalesSpecialist(EvidenceInterpreter(model))
        first, first_calls = interviews()
        second, _ = interviews()
        results = await specialist.assess_companies({'broken': first, 'healthy': second}, concurrency=1)
        self.assertEqual(set(results), {'broken', 'healthy'})
        self.assertEqual(results['broken'].status, 'api_error')
        self.assertEqual(results['broken'].model_calls, 1)
        self.assertEqual(results['healthy'].verdict, 'PASS')
        self.assertEqual(len(first_calls), 1)
        self.assertNotIn('secret', str(results['broken'].diagnostics))
        self.assertEqual(results['broken'].public_result()['points'], {4: 'FAIL'})
        self.assertIn('api_error', results['broken'].public_result()['summary'])

    async def test_tool_errors_do_not_become_investment_evidence(self):
        for answer in [RuntimeError('broken'), '', None, 'Interview limit reached: 10 interviews per company.',
                       "Unknown role 'customer'. Roles: supplier. (Not counted.)"]:
            with self.subTest(answer=answer):
                model = ScriptedModel(responses=[])
                tools, _ = interviews(customer=answer)
                result = await SalesSpecialist(EvidenceInterpreter(model)).assess('broken', tools)
                self.assertEqual(result.status, 'retrieval_error')
                self.assertEqual(result.model_calls, 0)
                self.assertEqual(result.verdict, 'FAIL')

    async def test_exhausted_uncertainty_is_honest_failure_not_assessed_fail(self):
        model = ScriptedModel(responses=[decision('UNCERTAIN')] * 3)
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('empty', tools)
        self.assertEqual(result.status, 'insufficient_evidence')
        self.assertEqual(result.verdict, 'FAIL')
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.model_calls, 3)
        self.assertIn('insufficient_evidence', result.public_result()['summary'])

    async def test_all_stages_can_recover_once_but_never_exceed_six_calls(self):
        invalid = AIMessage(content='bad')
        model = ScriptedModel(responses=[invalid, decision('UNCERTAIN'),
                                       invalid, decision('UNCERTAIN'), invalid, decision('FAIL')])
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('bounded', tools)
        self.assertEqual(result.model_calls, 6)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.verdict, 'FAIL')
        self.assertEqual(result.status, 'adjudicated')

    async def test_invented_reference_is_rejected_even_with_a_real_quote(self):
        model = ScriptedModel(responses=[decision(evidence_id='competitor:sales_team')] * 2)
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('wrong-source', tools)
        self.assertEqual(result.status, 'invalid_output')
        self.assertEqual(len(calls), 1)

    async def test_multiple_assessments_cannot_silently_select_the_first(self):
        response = AIMessage(content='', tool_calls=[
            dict(name='SalesAssessment', args=decision(), id='first'),
            dict(name='SalesAssessment', args=decision('FAIL'), id='second')])
        model = ScriptedModel(responses=[response, response])
        tools, calls = interviews()
        result = await SalesSpecialist(EvidenceInterpreter(model)).assess('duplicate', tools)
        self.assertEqual(result.status, 'invalid_output')
        self.assertEqual(len(calls), 1)

    async def test_model_timeout_has_no_transport_retry_or_extra_interview(self):
        from langchain_core.runnables import RunnableLambda
        async def blocked(_):
            await asyncio.Event().wait()
        interpreter = EvidenceInterpreter(ScriptedModel())
        interpreter._chain = RunnableLambda(blocked)
        tools, calls = interviews()
        with patch('fisher_agent.sales_specialist.MODEL_TIMEOUT_SECONDS', 0.01):
            result = await SalesSpecialist(interpreter).assess('timeout', tools)
        self.assertEqual(result.status, 'api_error')
        self.assertEqual(result.model_calls, 1)
        self.assertEqual(len(calls), 1)

    async def test_concurrent_companies_use_their_own_evidence(self):
        from langchain_core.runnables import RunnableLambda
        import json

        async def classify(messages):
            payload = json.loads(messages[1].content)
            self.assertEqual(len(payload), 1)
            source = payload[0]
            self.assertIn(source['company_id'], source['answer'])
            await asyncio.sleep(0)
            return dict(raw=AIMessage(content='', tool_calls=[dict(
                name='SalesAssessment', args=decision(), id='assessment')]),
                parsing_error=None, parsed=decision(quote=source['answer']))

        interpreter = EvidenceInterpreter(ScriptedModel())
        interpreter._chain = RunnableLambda(classify)
        tools_a, _ = interviews(customer='alpha salespeople provide knowledgeable advice.')
        tools_b, _ = interviews(customer='beta salespeople provide knowledgeable advice.')
        results = await SalesSpecialist(interpreter).assess_companies({'alpha': tools_a, 'beta': tools_b})
        for name, result in results.items():
            self.assertEqual(result.status, 'assessed')
            self.assertEqual(result.interviews_used, 1)
            self.assertEqual(result.evidence[0].company_id, name)
            self.assertIn(name, result.assessments[0].evidence)

    async def test_company_deadline_preserves_result(self):
        from langchain_core.runnables import RunnableLambda

        async def blocked(_):
            await asyncio.Event().wait()

        interpreter = EvidenceInterpreter(ScriptedModel())
        interpreter._chain = RunnableLambda(blocked)
        tools, calls = interviews()
        with patch('fisher_agent.sales_specialist.COMPANY_DEADLINE_SECONDS', 0.01):
            result = await SalesSpecialist(interpreter).assess('slow', tools)
        self.assertEqual(result.status, 'deadline')
        self.assertEqual(result.verdict, 'FAIL')
        self.assertEqual(len(calls), 1)

    async def test_cancellation_propagates(self):
        model = ScriptedModel(responses=[asyncio.CancelledError()])
        # Cancellation belongs to the caller, not the investment failure policy.
        from langchain_core.runnables import RunnableLambda
        async def cancel(_):
            raise asyncio.CancelledError()
        interpreter = EvidenceInterpreter(model)
        interpreter._chain = RunnableLambda(cancel)
        tools, _ = interviews()
        with self.assertRaises(asyncio.CancelledError):
            await SalesSpecialist(interpreter).assess('cancelled', tools)


if __name__ == '__main__':
    unittest.main()
