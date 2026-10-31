"""Model configuration at the construction boundary; no provider requests."""
import unittest
from unittest.mock import patch

import hw3
from fisher_agent.runtime import build_sales_specialist
from test_sales_specialist import ScriptedModel


class SalesRuntimeTests(unittest.TestCase):
    def test_only_permitted_model_is_constructed_with_sdk_retries_disabled(self):
        with patch('fisher_agent.runtime.ChatDeepSeek', return_value=ScriptedModel()) as model:
            build_sales_specialist()
        config = model.call_args.kwargs
        self.assertEqual(config['model'], hw3.MODEL_NAME)
        self.assertEqual(config['model'], 'deepseek-v4-flash')
        self.assertEqual(config['temperature'], 0)
        self.assertEqual(config['max_retries'], 0)
        self.assertEqual(config['timeout'], 20)
