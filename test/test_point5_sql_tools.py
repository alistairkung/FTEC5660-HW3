"""Synthetic fixtures exercised through the unchanged lecturer LangChain tool."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zlib

import hw3
from fisher_agent.point5.historical_margin_strategy import HistoricalMarginStrategy
from fisher_agent.point5.industry_margin_strategy import IndustryMarginStrategy


class Point5SQLToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        (self.folder / 'interviews.dat').write_bytes(zlib.compress(b'{}'))

    def make_fixture(self, *, missing_month=False, null_amount=False, bad_cost=False):
        # Only write known synthetic inputs here; assessments read them through sql_query.
        with closing(sqlite3.connect(self.folder / 'company.db')) as database, database:
            database.executescript('''
                CREATE TABLE orders(order_date TEXT, amount);
                CREATE TABLE monthly_costs(month TEXT, cost_of_sales, selling_admin, research_development);
                CREATE TABLE company(industry TEXT);
                CREATE TABLE industry_medians(industry TEXT, operating_margin_pct);
                INSERT INTO company VALUES ('selected');
                INSERT INTO industry_medians VALUES ('unrelated', 99), ('selected', 20);
            ''')
            for year in (2023, 2024, 2025):
                for month in range(1, 13):
                    database.execute('INSERT INTO orders VALUES (?, ?)',
                                     (f'{year}-{month:02}-01', 100))
                    if missing_month and year == 2024 and month == 1:
                        continue
                    database.execute('INSERT INTO monthly_costs VALUES (?, ?, 20, 10)',
                                     (f'{year}-{month:02}', 'invalid' if bad_cost else 50))
            if null_amount:
                database.execute("INSERT INTO orders VALUES ('2025-01-02', NULL)")
        return next(tool for tool in hw3.make_tools(self.folder) if tool.name == 'sql_query')

    def test_actual_sql_aggregates_without_multiplying_rows_and_joins_own_industry(self):
        tool = self.make_fixture()
        for strategy in (IndustryMarginStrategy(), HistoricalMarginStrategy()):
            with self.subTest(strategy=strategy.name):
                result = strategy.evaluate('synthetic', tool)
                self.assertEqual(result.verdict, 'PASS')
                self.assertEqual(result.margins[-1].revenue, 1200)
                self.assertEqual(result.margins[-1].operating_costs, 960)
                self.assertEqual(result.margins[-1].margin_pct, 20)

    def test_missing_month_in_middle_year_rejected(self):
        result = HistoricalMarginStrategy().evaluate('synthetic', self.make_fixture(missing_month=True))
        self.assertEqual(result.error.code, 'missing_data')

    def test_null_order_is_not_silently_hidden_by_sum(self):
        result = IndustryMarginStrategy().evaluate('synthetic', self.make_fixture(null_amount=True))
        self.assertEqual(result.error.code, 'invalid_number')

    def test_text_cost_is_not_silently_coerced_by_sqlite(self):
        result = IndustryMarginStrategy().evaluate('synthetic', self.make_fixture(bad_cost=True))
        self.assertEqual(result.error.code, 'invalid_number')
