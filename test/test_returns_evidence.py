"""Exact pooled returns rule at the supplied-SQL decoding boundary."""
from dataclasses import replace
import sqlite3
import unittest

from fisher_agent.point14.returns_evidence import RETURNS_QUERY, decode_quarters, compare_quarters


def raw_rows(rows):
    return 'quarter | row_count | month_count | valid_count | units_shipped | units_returned\n' + '\n'.join(
        ' | '.join(map(str, row)) for row in rows)


def baseline_rows():
    return [(f'{2024 + i//4}Q{i%4+1}', 3, 3, 3, 1000, 10) for i in range(2,10)]


class ReturnsEvidenceTests(unittest.TestCase):
    def test_only_the_eight_needed_quarters_are_required(self):
        rows=[(f'{2024+i//4}Q{i%4+1}',3,3,3,1000,10) for i in range(2,10)]
        self.assertEqual(len(decode_quarters(raw_rows(rows),'example','sql:test')),8)
        self.assertEqual(len(compare_quarters(decode_quarters(raw_rows(rows),'example','sql:test'))),4)

    def test_exact_threshold_and_pooled_baseline(self):
        rows = baseline_rows()
        rows[4] = ('2025Q3',3,3,3,1000,20)
        quarters = decode_quarters(raw_rows(rows), 'example', 'sql:test')
        comparisons = compare_quarters(quarters)
        self.assertEqual([c.period for c in comparisons if c.anomalous], ['2025Q3'])
        self.assertEqual(comparisons[0].baseline_returned, 40)
        self.assertEqual(comparisons[0].baseline_shipped, 4000)

    def test_company_and_sql_provenance_are_preserved_and_mixing_rejected(self):
        quarters = decode_quarters(raw_rows(baseline_rows()), 'example', 'sql:test')
        comparisons = compare_quarters(quarters)
        self.assertTrue(all(c.company_id == 'example' and c.source_id == 'sql:test' for c in comparisons))
        self.assertEqual(comparisons[0].current_rate, 1)
        self.assertEqual(comparisons[0].baseline_rate, 1)
        for changed in (replace(quarters[0],company_id='other'),replace(quarters[0],source_id='other')):
            with self.assertRaises(ValueError): compare_quarters((changed,)+quarters[1:])

    def test_baseline_is_ratio_of_pooled_counts_and_zero_baseline_positive_is_anomaly(self):
        rows=baseline_rows()
        for index,shipped in zip(range(0,4),(1,1,1,1000)):
            rows[index]=(rows[index][0],3,3,3,shipped,1)
        current=compare_quarters(decode_quarters(raw_rows(rows),'example','sql:test'))[0]
        self.assertEqual((current.baseline_returned,current.baseline_shipped),(4,1003))
        self.assertTrue(current.anomalous)  # Average-of-percentages would miss this.
        zeros=[(p,n,m,v,s,0) for p,n,m,v,s,r in baseline_rows()]
        zeros[4]=('2025Q3',3,3,3,1000,1)
        first=compare_quarters(decode_quarters(raw_rows(zeros),'example','sql:test'))[0]
        self.assertTrue(first.anomalous)
        self.assertIsNone(first.ratio)
        self.assertTrue(first.zero_baseline)

    def test_integer_products_do_not_round_a_just_below_threshold_rate_up(self):
        rows=baseline_rows();n=10**16
        for index in range(4):rows[index]=(rows[index][0],3,3,3,n//2,n//4)
        rows[3]=(rows[3][0],3,3,3,n//2+2,n//4)
        rows[4]=('2025Q3',3,3,3,n,n-1)
        comparison=compare_quarters(decode_quarters(raw_rows(rows),'example','sql:test'))[0]
        self.assertEqual(comparison.ratio,2)  # Display rounds up; exact products differ by two.
        self.assertFalse(comparison.anomalous)

    def test_zero_baseline_zero_current_is_authorized_no_anomaly(self):
        quarters = decode_quarters(raw_rows([(p,n,m,v,s,0) for p,n,m,v,s,r in baseline_rows()]), 'example', 'sql:test')
        self.assertTrue(all(not c.anomalous and c.ratio is None for c in compare_quarters(quarters)))

    def test_invalid_duplicate_missing_and_truncated_rows_reject(self):
        cases = [(baseline_rows()[:-1],'incomplete_returns_history'),
                 (baseline_rows()+[baseline_rows()[0]],'incomplete_returns_history')]
        for first,code in (
            (('2024Q3',4,3,3,1000,10),'invalid_monthly_returns'),
            (('2024Q3',3,3,2,1000,10),'invalid_monthly_returns'),
            (('2024Q3',3,3,3,1000,-1),'invalid_returns_count'),
            (('2024Q3',3,3,3,1000,1001),'inconsistent_returns_count'),
            (('2024Q3',3,3,3,0,0),'undefined_returns_rate'),
            (('2024Q3',3,3,3,1000,'1.5'),'invalid_returns_count'),
        ):
            cases.append(([first]+baseline_rows()[1:],code))
        for changed,code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError,'^'+code+'$'):
                compare_quarters(decode_quarters(raw_rows(changed),'example','sql:test'))
        with self.assertRaisesRegex(ValueError,'^truncated_returns$'):
            decode_quarters(raw_rows(baseline_rows())+'\n... more rows not shown (limit 50)','example','sql:test')

    def test_sql_rejects_hidden_bad_duplicate_and_integral_aggregation(self):
        database = sqlite3.connect(':memory:')
        database.execute('CREATE TABLE returns(month TEXT, units_shipped, units_returned)')
        for year in (2024,2025,2026):
            for month in range(1,13 if year<2026 else 7):
                database.execute('INSERT INTO returns VALUES(?,?,?)',(f'{year}-{month:02}',100,1))
        def read():
            cursor = database.execute(RETURNS_QUERY)
            return raw_rows(cursor.fetchall())
        self.assertEqual(len(decode_quarters(read(),'example','sql:test')),8)
        database.execute("INSERT INTO returns VALUES('2025-07',100,NULL)")
        with self.assertRaisesRegex(ValueError,'^invalid_monthly_returns$'):
            decode_quarters(read(),'example','sql:test')
        database.execute('DELETE FROM returns WHERE rowid=(SELECT MAX(rowid) FROM returns)')
        for invalid in (-1,0.5,None,'text',101):
            database.execute("UPDATE returns SET units_returned=? WHERE month='2025-07'",(invalid,))
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError,'^invalid_monthly_returns$'):
                decode_quarters(read(),'example','sql:test')
        database.close()
