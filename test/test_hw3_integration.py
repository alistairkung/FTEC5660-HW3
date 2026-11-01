"""Exercise student wiring and unchanged lecturer normalization/CSV offline."""
from contextlib import redirect_stdout
import csv
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import hw3
from fisher_agent.point14 import Point14ReturnsStrategy
from test_company_analyzer import company_tools
from test_sales_specialist import ScriptedModel, decision


class HomeworkIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_writes_exactly_three_grounded_points(self):
        model = ScriptedModel(responses=[decision()])
        tools = company_tools()

        def labels_after_prediction(_):
            self.assertEqual(len(model.seen), 1)
            self.assertEqual(len(tools[-1].queries), 3)
            return {'sample': {'points': {'4': 'PASS', '5': 'PASS', '14': 'PASS'}}}

        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                with patch('hw3.company_folders', return_value=[Path('sample')]), \
                        patch('hw3.make_tools', return_value=tools), \
                        patch('hw3.read_ground_truth', side_effect=labels_after_prediction), \
                        patch('langchain_deepseek.ChatDeepSeek', return_value=model), \
                        patch('fisher_agent.bootstrap.build_returns_strategy',
                              return_value=Point14ReturnsStrategy()) as returns_factory, \
                        redirect_stdout(io.StringIO()):
                    self.assertEqual(await hw3.run(Path(directory)), 0)
                    returns_factory.assert_called_once_with(hw3.MODEL_NAME, None)
                with Path('results.csv').open() as handle:
                    row = next(csv.DictReader(handle))
            finally:
                os.chdir(previous)
        self.assertEqual(row['points'], '4:PASS 5:PASS 14:PASS')
        self.assertEqual(row['points_correct'], '3/3')
        self.assertNotIn('pending', row['summary'])
