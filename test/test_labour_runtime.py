"""The actual provider request explicitly disables thinking; no network needed."""
import json
import unittest
from unittest.mock import patch

import httpx
from langchain_deepseek import ChatDeepSeek

import hw3
from fisher_agent.labour_runtime import build_labour_specialist
from test_labour_specialist import decision, interviews


class LabourRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_required_model_and_non_thinking_config_reach_the_wire(self):
        requests = []

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(payload['thinking'], {'type': 'disabled'})
            self.assertEqual(payload['model'], 'deepseek-v4-flash')
            self.assertEqual(payload['tool_choice'], {
                'type': 'function', 'function': {'name': 'LabourAssessment'}})
            return httpx.Response(200, json={
                'id': 'synthetic-labour', 'object': 'chat.completion', 'created': 0,
                'model': hw3.MODEL_NAME,
                'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'content': '', 'tool_calls': [{
                        'id': 'call', 'type': 'function',
                        'function': {'name': 'LabourAssessment', 'arguments': json.dumps(decision())}}]}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            def construct(**kwargs):
                self.assertEqual(kwargs['timeout'], 20)
                self.assertEqual(kwargs['max_retries'], 0)
                return ChatDeepSeek(**kwargs, api_key='synthetic', http_async_client=client)

            with patch('fisher_agent.labour_runtime.ChatDeepSeek', side_effect=construct):
                specialist = build_labour_specialist()
            tools, _ = interviews()
            run = await specialist.assess('synthetic', tools)
        self.assertEqual((run.point_result.verdict, len(requests)), ('PASS', 1))
