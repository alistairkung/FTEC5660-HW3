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
from test_company_analyzer import company_tools
from test_sales_specialist import ScriptedModel, decision


class HomeworkIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_writes_two_grounded_points_and_honest_missing_point14(self):
        model = ScriptedModel(responses=[decision()])
        tools = company_tools()

        def labels_after_prediction(_):
            self.assertEqual(len(model.seen), 1)
            self.assertEqual(len(tools[-1].queries), 2)
            return {'sample': {'points': {'4': 'PASS', '5': 'PASS', '14': 'FAIL'}}}

        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                with patch('hw3.company_folders', return_value=[Path('sample')]), \
                        patch('hw3.make_tools', return_value=tools), \
                        patch('hw3.read_ground_truth', side_effect=labels_after_prediction), \
                        patch('fisher_agent.runtime.ChatDeepSeek', return_value=model), \
                        redirect_stdout(io.StringIO()):
                    self.assertEqual(await hw3.run(Path(directory)), 0)
                with Path('results.csv').open() as handle:
                    row = next(csv.DictReader(handle))
            finally:
                os.chdir(previous)
        self.assertEqual(row['points'], '4:PASS 5:PASS 14:missing')
        self.assertEqual(row['points_correct'], '2/3')
        self.assertIn('Point 14 pending', row['summary'])
