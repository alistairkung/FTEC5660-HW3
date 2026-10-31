"""Exercise the model's serialized HTTP request without network or credentials."""
import json
import unittest
from unittest.mock import patch

import httpx
from langchain_deepseek import ChatDeepSeek

from fisher_agent.point14.runtime import build_transparency_specialist
from hw3 import MODEL_NAME
from observability import Tracing


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_disables_thinking_in_the_serialized_request(self):
        requests = []

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(payload['model'], MODEL_NAME)
            self.assertEqual(payload.get('thinking'), {'type': 'disabled'})
            self.assertEqual(payload['max_tokens'], 3500)
            self.assertEqual(payload['temperature'], 0)
            return httpx.Response(200, json={
                'id': 'test-completion', 'object': 'chat.completion', 'created': 1,
                'model': MODEL_NAME,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{}'},
                             'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
            })

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as async_client:
                def configured_model(**kwargs):
                    return ChatDeepSeek(api_key='synthetic-test-key', http_client=client,
                                        http_async_client=async_client, **kwargs)

                with patch('fisher_agent.point14.runtime.ChatDeepSeek', side_effect=configured_model):
                    with Tracing() as tracing:
                        specialist = build_transparency_specialist(tracing)
                        response = await specialist.model.ainvoke('Return JSON only: {}')
                self.assertEqual(json.loads(response.content), {})
        self.assertEqual(len(requests), 1)
