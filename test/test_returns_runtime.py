"""Serialize the actual structured DeepSeek request without a network call."""
import json
import unittest
from unittest.mock import patch

import httpx
from langchain_deepseek import ChatDeepSeek

from fisher_agent.returns_disclosure import build_returns_strategy
import test_returns_disclosure as disclosure_tests


class ReturnsRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonthinking_function_calling_request_and_no_sdk_retries(self):
        requests=[]
        assessment=disclosure_tests.proposal().model_dump()
        def respond(request):
            payload=json.loads(request.content);requests.append(payload)
            self.assertEqual(payload['model'],'deepseek-v4-flash')
            self.assertEqual(payload['thinking'],{'type':'disabled'})
            self.assertEqual(payload['temperature'],0)
            self.assertEqual(payload['max_tokens'],600)
            self.assertEqual(payload['tool_choice'],{'type':'function','function':{'name':'DisclosureAssessment'}})
            self.assertEqual(payload['tools'][0]['function']['name'],'DisclosureAssessment')
            return httpx.Response(200,json={'id':'synthetic','object':'chat.completion','created':0,
                'model':'deepseek-v4-flash','choices':[{'index':0,'finish_reason':'tool_calls','message':{
                'role':'assistant','content':'','tool_calls':[{'id':'test','type':'function','function':{
                'name':'DisclosureAssessment','arguments':json.dumps(assessment)}}]}}],
                'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            def construct(**kwargs):
                self.assertEqual(kwargs['max_retries'],0)
                self.assertEqual(kwargs['timeout'],20)
                return ChatDeepSeek(**kwargs,api_key='synthetic-test-key',http_async_client=client)
            with patch('langchain_deepseek.ChatDeepSeek',side_effect=construct):
                strategy=build_returns_strategy()
            run=await strategy.assess('example',disclosure_tests.ReturnsStrategyTests().tools())
        self.assertEqual(run.point_result.verdict,'PASS')
        self.assertEqual(run.model_calls,1)
        self.assertEqual(len(requests),1)
