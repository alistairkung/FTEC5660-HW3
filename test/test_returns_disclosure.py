"""Relevant-call provenance and event aggregation, with injected models/tools."""
import unittest
import asyncio
from unittest.mock import patch
from langchain_core.messages import AIMessage

from fisher_agent.returns_disclosure.records import DisclosureAssessment, SourceEvidence
from fisher_agent.returns_disclosure.point14_returns_strategy import validate_call, validate_assessment

TEXT = '''# Example: earnings call, third quarter 2025

Date: 2025-10-29

Olivia Chen (Chief Financial Officer): Returns rose sharply this quarter. We are replacing affected units.

Analyst: Was the return problem serious?

Olivia Chen: We are working on it.
'''


def call(text=TEXT):
    return validate_call('2025Q3', 'earnings_call_2025q3.md', '2025-10-29',
        SourceEvidence('doc:q3','example','read_document',{'name':'earnings_call_2025q3.md'},text))


def proposal(**changes):
    return DisclosureAssessment(document='earnings_call_2025q3.md', quarter='2025Q3',
        classification=changes.get('classification','ACKNOWLEDGED'), quotation=changes.get('quotation',
        'Returns rose sharply this quarter.'), speaker=changes.get('speaker','Olivia Chen (Chief Financial Officer)'),
        full_call_inspected=changes.get('full_call_inspected',True), reason='The same-quarter setback is discussed.')


class ReturnsDisclosureValidationTests(unittest.TestCase):
    def test_management_exact_quote_and_source_derived_alias(self):
        self.assertEqual(validate_assessment(proposal(),call()).classification,'ACKNOWLEDGED')
        self.assertEqual(validate_assessment(proposal(quotation='We are working on it.',speaker='Olivia Chen'),call()).speaker,
                         'Olivia Chen')

    def test_blank_analyst_fabricated_and_crossspeaker_quotes_reject(self):
        for quote,speaker in (
            ('   ','Olivia Chen'),('Returns doubled.','Olivia Chen'),
            ('Was the return problem serious?','Analyst'),
            ('affected units.\n\nAnalyst: Was the return problem serious?','Olivia Chen'),
        ):
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                validate_assessment(proposal(quotation=quote,speaker=speaker),call())

    def test_negative_needs_full_call_inspection_and_no_fabricated_quote(self):
        negative=proposal(classification='NOT_ACKNOWLEDGED',quotation=None,speaker=None)
        self.assertEqual(validate_assessment(negative,call()).classification,'NOT_ACKNOWLEDGED')
        for changes in ({'full_call_inspected':False},{'quotation':'no statement found'}, {'speaker':'Analyst'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_assessment(negative.model_copy(update=changes),call())

    def test_wrong_quarter_missing_date_truncation_and_heading_reject(self):
        for text in (TEXT.replace('third quarter','fourth quarter'),TEXT.replace('2025-10-29','2025-07-01'),
                     TEXT.replace('Date: 2025-10-29',''),TEXT+'\n[truncated]'):
            with self.subTest(text=text), self.assertRaises(ValueError):call(text)
        with self.assertRaises(ValueError):
            validate_assessment(proposal(quotation='Subheading'),call(TEXT+'\n# Subheading\n'))

    def test_indented_heading_ends_speech_until_a_new_speaker_label(self):
        text=TEXT+'\n   ## Returns rose sharply this quarter.\nUnlabelled continuation.\n\nOlivia Chen: We have acted.\n'
        document=call(text)
        for quote in ('Returns rose sharply this quarter.','Unlabelled continuation.'):
            with self.subTest(quote=quote),self.assertRaisesRegex(ValueError,'^invalid_management_quotation$'):
                validate_assessment(proposal(quotation=quote,speaker='Olivia Chen'),document)
        self.assertEqual(validate_assessment(proposal(quotation='We have acted.',speaker='Olivia Chen'),document)
                         .quotation,'We have acted.')

class Tool:
    def __init__(self,name,answer):
        self.name,self.answer,self.calls=name,answer,0
    async def ainvoke(self,args,config=None):
        self.calls+=1
        if isinstance(self.answer,Exception):raise self.answer
        return self.answer(args) if callable(self.answer) else self.answer


class Model:
    def __init__(self,assessments):
        self.assessments=list(assessments)
        self.calls=0
        self.structured_options=None
    def with_structured_output(self,schema,**options):
        self.structured_options=options
        return self
    async def ainvoke(self,messages,config=None):
        assessment=self.assessments[self.calls]
        self.calls+=1
        if isinstance(assessment,Exception):raise assessment
        raw=AIMessage(content='',tool_calls=[{'id':'x','name':'DisclosureAssessment',
            'args':assessment.model_dump()}],usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15})
        return {'raw':raw,'parsed':assessment,'parsing_error':None}


class ReturnsStrategyTests(unittest.IsolatedAsyncioTestCase):
    def tools(self):
        from test_returns_evidence import baseline_rows,raw_rows
        rows=baseline_rows();rows[4]=('2025Q3',3,3,3,1000,20)
        return [Tool('sql_query',raw_rows(rows)),Tool('list_documents',
            'earnings_call_2025q3.md: Example (Date: 2025-10-29)'),Tool('read_document',TEXT)]

    async def test_anomaly_ack_negative_and_uncertain_use_one_relevant_full_call(self):
        from fisher_agent.returns_disclosure.point14_returns_strategy import Point14ReturnsStrategy
        for classification,verdict,status in (('ACKNOWLEDGED','PASS','complete'),
            ('NOT_ACKNOWLEDGED','FAIL','complete'),('UNCERTAIN',None,'insufficient_evidence')):
            with self.subTest(classification=classification):
                assessment=proposal(classification=classification,
                    quotation='Returns rose sharply this quarter.' if classification=='ACKNOWLEDGED' else None,
                    speaker='Olivia Chen (Chief Financial Officer)' if classification=='ACKNOWLEDGED' else None)
                model=Model([assessment]);tools=self.tools()
                run=await Point14ReturnsStrategy(model).assess('example',tools)
                self.assertEqual((run.point_result.verdict,run.point_result.status),(verdict,status))
                self.assertEqual([tool.calls for tool in tools],[1,1,1])
                self.assertEqual(run.model_calls,1)
                self.assertEqual(model.structured_options,{'method':'function_calling','include_raw':True})
                self.assertEqual(run.usage['total_tokens'],15)

    async def test_no_anomaly_is_scoped_pass_without_documents_or_model(self):
        from fisher_agent.returns_disclosure.point14_returns_strategy import Point14ReturnsStrategy
        from test_returns_evidence import baseline_rows,raw_rows
        sql=Tool('sql_query',raw_rows(baseline_rows()))
        listing=Tool('list_documents',AssertionError('must not list'))
        reader=Tool('read_document',AssertionError('must not read'))
        run=await Point14ReturnsStrategy().assess('example',[sql,listing,reader])
        self.assertEqual(run.point_result.verdict,'PASS')
        self.assertEqual(run.point_result.status,'complete')
        self.assertEqual(run.model_calls,0)
        self.assertEqual((sql.calls,listing.calls,reader.calls),(1,0,0))
        self.assertEqual(run.point_result.point,14)
        self.assertEqual(len(run.comparisons),4)

    async def test_invalid_quote_repairs_once_without_retrieving_again(self):
        from fisher_agent.returns_disclosure import Point14ReturnsStrategy
        model=Model([proposal(quotation='invented'),proposal()]);tools=self.tools()
        run=await Point14ReturnsStrategy(model).assess('example',tools)
        self.assertEqual(run.point_result.verdict,'PASS')
        self.assertEqual((run.model_calls,run.format_repairs),(2,1))
        self.assertEqual([tool.calls for tool in tools],[1,1,1])
        invalid=await Point14ReturnsStrategy(Model([proposal(quotation='invented')]*2)).assess('example',self.tools())
        self.assertIsNone(invalid.point_result.verdict)
        self.assertEqual(invalid.point_result.status,'error')
        self.assertEqual(invalid.model_calls,2)

    async def test_verified_negative_survives_neighbor_retrieval_error(self):
        from fisher_agent.returns_disclosure import Point14ReturnsStrategy
        from test_returns_evidence import baseline_rows,raw_rows
        rows=baseline_rows();rows[4]=('2025Q3',3,3,3,1000,20);rows[5]=('2025Q4',3,3,3,1000,40)
        tools=self.tools();tools[0].answer=raw_rows(rows)
        tools[1].answer+='\nearnings_call_2025q4.md: Example (Date: 2026-01-29)'
        def reader(args):
            if '2025q4' in args['name']:raise ValueError('broken neighboring call')
            return TEXT
        tools[2].answer=reader
        model=Model([proposal(classification='NOT_ACKNOWLEDGED',quotation=None,speaker=None)])
        run=await Point14ReturnsStrategy(model).assess('example',tools)
        self.assertEqual((run.point_result.verdict,run.point_result.status),('FAIL','complete'))
        self.assertIn('Other events remain unresolved',run.point_result.summary)
        self.assertTrue(any(d.stage=='2025Q4' for d in run.point_result.diagnostics))

    async def test_negative_with_uncertain_neighbor_retains_explicit_uncertainty(self):
        from fisher_agent.returns_disclosure import Point14ReturnsStrategy
        from test_returns_evidence import baseline_rows,raw_rows
        rows=baseline_rows();rows[4]=('2025Q3',3,3,3,1000,20);rows[5]=('2025Q4',3,3,3,1000,40)
        tools=self.tools();tools[0].answer=raw_rows(rows)
        tools[1].answer+='\nearnings_call_2025q4.md: Example (Date: 2026-01-29)'
        tools[2].answer=lambda args: (TEXT.replace('third quarter 2025','fourth quarter 2025')
            .replace('2025-10-29','2026-01-29') if '2025q4' in args['name'] else TEXT)
        first=proposal(classification='NOT_ACKNOWLEDGED',quotation=None,speaker=None)
        second=proposal(classification='UNCERTAIN',quotation=None,speaker=None).model_copy(
            update={'document':'earnings_call_2025q4.md','quarter':'2025Q4'})
        run=await Point14ReturnsStrategy(Model([first,second])).assess('example',tools)
        self.assertEqual(run.point_result.verdict,'FAIL')
        self.assertIn('Other events remain unresolved',run.point_result.summary)
        self.assertTrue(any(d.code=='disclosure_uncertain' and d.stage=='2025Q4'
                            for d in run.point_result.diagnostics))

    async def test_sql_failure_missing_call_and_api_error_are_not_investment_fails(self):
        from fisher_agent.returns_disclosure import Point14ReturnsStrategy
        for stage in ('sql','listing','api'):
            tools=self.tools();model=Model([RuntimeError('provider failure')])
            if stage=='sql':tools[0].answer='SQL error: broken'
            if stage=='listing':tools[1].answer=''
            run=await Point14ReturnsStrategy(model).assess('example',tools)
            with self.subTest(stage=stage):
                self.assertIsNone(run.point_result.verdict)
                self.assertEqual(run.point_result.status,'error')
                self.assertLessEqual(run.model_calls,1)
                if stage=='api':
                    self.assertTrue(any(d.code=='model_api_error' for d in run.point_result.diagnostics))

    async def test_company_deadline_and_cancellation_propagation(self):
        from fisher_agent.returns_disclosure import Point14ReturnsStrategy
        tools=self.tools()
        async def sleeping(args,config=None):await asyncio.sleep(10)
        tools[0].ainvoke=sleeping
        module='fisher_agent.returns_disclosure.point14_returns_strategy'
        with patch(module+'.COMPANY_DEADLINE_SECONDS',0.001):
            run=await Point14ReturnsStrategy().assess('example',tools)
        self.assertIsNone(run.point_result.verdict)
        self.assertTrue(any(d.code=='deadline' for d in run.point_result.diagnostics))
        task=asyncio.create_task(Point14ReturnsStrategy().assess('example',tools))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task

    async def test_batch_bounds_workers_and_isolates_company_errors(self):
        from fisher_agent.returns_disclosure import Point14ReturnsStrategy
        from test_returns_evidence import raw_rows,baseline_rows
        state={'active':0,'peak':0}
        companies={}
        for name in ('one','two','three','broken'):
            tool=Tool('sql_query','')
            async def query(args,config=None,company=name):
                state['active']+=1;state['peak']=max(state['peak'],state['active'])
                await asyncio.sleep(0.001)
                state['active']-=1
                return 'SQL error: broken' if company=='broken' else raw_rows(baseline_rows())
            tool.ainvoke=query;companies[name]=[tool]
        strategy=Point14ReturnsStrategy()
        runs=await strategy.assess_companies(companies,concurrency=2)
        self.assertEqual(state['peak'],2)
        self.assertEqual(set(runs),set(companies))
        self.assertIsNone(runs['broken'].point_result.verdict)
        for company in ('one','two','three'):
            self.assertEqual(runs[company].point_result.verdict,'PASS')
            self.assertTrue(all(p.company_id==company for p in runs[company].point_result.provenance))
        with self.assertRaises(ValueError):await strategy.assess_companies(companies,concurrency=3)
