"""Model configuration at the construction boundary; no provider requests."""
import json
import unittest
from unittest.mock import patch

import httpx
from langchain_deepseek import ChatDeepSeek

import hw3
from fisher_agent.bootstrap import build_sales_specialist
from test_sales_specialist import ScriptedModel, interviews


class SalesRuntimeTests(unittest.TestCase):
    def test_only_permitted_model_is_constructed_with_sdk_retries_disabled(self):
        with patch('langchain_deepseek.ChatDeepSeek', return_value=ScriptedModel()) as model:
            build_sales_specialist(hw3.MODEL_NAME)
        config = model.call_args.kwargs
        self.assertEqual(config['model'], hw3.MODEL_NAME)
        self.assertEqual(config['model'], 'deepseek-v4-flash')
        self.assertEqual(config['temperature'], 0)
        self.assertEqual(config['max_retries'], 0)
        self.assertEqual(config['timeout'], 20)
        self.assertEqual(config['extra_body'], {'thinking': {'type': 'disabled'}})


class SalesRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_request_disables_thinking_on_the_wire(self):
        """Exercise LangChain and SDK serialization, without contacting DeepSeek."""
        requests = []
        quote = 'They help us select the right products.'
        assessment = dict(verdict='PASS', evidence=quote,
                          evidence_id='customer:sales_team', reasoning='Knowledgeable sales support.')

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(payload.get('thinking'), {'type': 'disabled'})
            self.assertEqual(payload['model'], hw3.MODEL_NAME)
            self.assertEqual(payload['tool_choice'], {
                'type': 'function', 'function': {'name': 'SalesAssessment'}})
            self.assertEqual(payload['tools'][0]['function']['name'], 'SalesAssessment')
            return httpx.Response(200, json={
                'id': 'synthetic-sales-response', 'object': 'chat.completion', 'created': 0,
                'model': hw3.MODEL_NAME,
                'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'content': '', 'tool_calls': [{
                        'id': 'synthetic-sales-call', 'type': 'function',
                        'function': {'name': 'SalesAssessment', 'arguments': json.dumps(assessment)},
                    }],
                }}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20},
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            def construct(**kwargs):
                return ChatDeepSeek(**kwargs, api_key='synthetic-test-key', http_async_client=client)

            with patch('langchain_deepseek.ChatDeepSeek', side_effect=construct):
                specialist = build_sales_specialist(hw3.MODEL_NAME)
            tools, calls = interviews(customer=quote)
            result = await specialist.assess('synthetic', tools)
        self.assertEqual(result.status, 'assessed')
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(calls, [{'role': 'customer', 'topic': 'sales_team'}])
        self.assertEqual(len(requests), 1)
        self.assertEqual(result.model_calls, 1)
