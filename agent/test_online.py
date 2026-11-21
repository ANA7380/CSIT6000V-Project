import hashlib,json,ssl,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from chat_agent import ChatAgent,SYSTEM
from tool_registry import validate,TOOLS
from web_tools import WebTools,public_url,fetch_url,relevant,tls_context
from evidence import validate_answer,GroundingError,view
from web_worker import process
from session_store import atomic_json

ROOT=Path(__file__).resolve().parents[1]

def response(content):return {'choices':[{'message':{'content':json.dumps(content)}}]}

def fixture_page(url,text,content_type='text/html'):
 return dict(url=url,retrieved_at='2026-11-21T00:00:00+00:00',text=text,content_type=content_type)

class OnlineTests(unittest.TestCase):
 def test_prompt_and_catalog_allow_external_stocks(self):
  self.assertIn('ANY company',SYSTEM);self.assertIn('Never reject a request merely',SYSTEM)
  self.assertEqual(len(TOOLS),10)
  validate('market_history',{'ticker':'MSFT','window':60})
  with self.assertRaises(ValueError):validate('web_search',{'query':'MSFT','shell':'x'})
  with self.assertRaises(ValueError):validate('market_history',{'ticker':'MSFT','window':True})

 def test_private_urls_and_credentials_denied(self):
  for url in ('file:///etc/passwd','http://127.0.0.1/','http://[::1]/','http://169.254.169.254/','http://localhost/','https://name:secret@example.com','https://example.com:8080'):
   with self.subTest(url=url),self.assertRaises(ValueError):public_url(url,resolve=False)
  with patch('web_tools.socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]):
   with self.assertRaises(ValueError):public_url('https://outside.example/')

 def test_dns_failure_is_repairable_tool_error(self):
  import socket
  with patch('web_tools.socket.getaddrinfo',side_effect=socket.gaierror('DNS unavailable')):
   with self.assertRaisesRegex(ValueError,'DNS lookup failed'):fetch_url('https://public.example/')

 def test_redirect_is_revalidated(self):
  class Reply:
   status=302
   def getheader(self,key):return 'http://169.254.169.254/metadata'
  class Conn:
   def __init__(self,*a,**kw):self.sock=None
   def request(self,*a,**kw):pass
   def getresponse(self):return Reply()
   def close(self):pass
  with patch('web_tools.socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',80))]),patch('web_tools.socket.create_connection'),patch('web_tools.http.client.HTTPConnection',Conn):
   with self.assertRaisesRegex(ValueError,'not allowed'):fetch_url('http://public.example/')

 def test_tls_is_verified(self):
  ctx=tls_context();self.assertEqual(ctx.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(ctx.check_hostname)

 def test_web_extraction_omits_script_and_keeps_source(self):
  content='<title>Official issuer</title><script>steal secrets</script><p>'+('Revenue evidence and company disclosures. '*10)+'</p>'
  tools=WebTools(lambda url:fixture_page(url,content));r=tools.read_webpage('https://issuer.example/')
  self.assertNotIn('steal',r['text']);self.assertEqual(r['sources'][0]['url'],'https://issuer.example/')
  e=view({'id':'E1','tool':'read_webpage','arguments':{'url':'https://issuer.example/'},'result':r})
  self.assertIsNone(e['ranking']);self.assertTrue(e['page_excerpt']);self.assertTrue(e['sources'])

 def test_challenge_is_not_evidence(self):
  tools=WebTools(lambda url:fixture_page(url,'<p>Verify you are human</p>'*20))
  with self.assertRaisesRegex(ValueError,'challenge'):tools.read_webpage('https://issuer.example/')

 def test_search_rejects_irrelevant_then_falls_back(self):
  def fetch(url):
   if 'search.brave' in url:return fixture_page(url,'<a href="https://unrelated.example/">Unrelated cartoons</a>')
   if 'google.com/search' in url:return fixture_page(url,'<a href="https://microsoft.com/ir">Microsoft investor relations</a>')
   raise AssertionError(url)
  r=WebTools(fetch).web_search('Microsoft MSFT investor relations')
  self.assertEqual(r['provider'],'google');self.assertEqual(len(r['warnings']),1)
  self.assertFalse(relevant('Microsoft MSFT investor relations','cartoons investor relations'))

 def test_numeric_prose_allowed_with_structural_citation_checks(self):
  e=[{'id':'E1','tool':'read_webpage','result':{'text':'Reported revenue was 27.356495% in 2026.'}}]
  validate_answer('Reported 27.36% in 2026. [E1]',e,require_evidence=True)
  validate_answer('Derived scenario: 99% in 2027. [E1]',e)
  with self.assertRaises(GroundingError):validate_answer('Revenue was 27.36%.',e,require_evidence=True)
  with self.assertRaises(GroundingError):validate_answer('See https://invented.example [E1]',e)

 def test_rss_dates_are_normalized_for_grounded_answers(self):
  rss='<rss><channel><item><title>Microsoft FY27 investor report</title><link>https://issuer.example/report</link><pubDate>Wed, 28 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
  def fetch(url):
   if 'news.google.com' in url:return fixture_page(url,rss,'application/xml')
   return fixture_page(url,'<p>No results</p>')
  r=WebTools(fetch).web_search('Microsoft MSFT investor relations')
  self.assertTrue(r['results'][0]['published_at'].startswith('2026-10-28'))
  e=[dict(id='E1',tool='web_search',result=r)]
  validate_answer('Published 2026-10-28. [E1]',e,require_evidence=True)

 def test_list_markers_are_not_fact_values(self):
  e=[dict(id='E1',tool='read_webpage',result={'text':'Issuer primary source.'})]
  validate_answer('1. The issuer source is available. [E1]\n2) Read the disclosure. [E1]',e)
  validate_answer('1. Scenario change: 99%. [E1]',e)
  with self.assertRaises(GroundingError):validate_answer('Result [E999]',e)

 def test_external_agent_loop_and_snapshot(self):
  calls=[]
  def model(messages,*a,**kw):
   calls.append(messages)
   if len(calls)==1:return response({'tool':'search_stocks','arguments':{'query':'Apple'}})
   return response({'answer':'Apple is identified by the retrieved symbol record. [E1]','evidence_ids':['E1']})
  with tempfile.TemporaryDirectory() as temp:
   agent=ChatAgent('http://localhost:42866/v1',Path(temp)/'trace.jsonl',call=model)
   agent.web.search_stocks=lambda query:dict(kind='stock_lookup',quotes=[dict(symbol='AAPL',longname='Apple')],sources=[dict(title='Lookup',url='https://finance.yahoo.com/')])
   answer=agent.ask('Tell me about Apple outside the old dataset.')
   self.assertFalse(agent.last_response['fallback']);self.assertEqual(len(calls),2)
   self.assertEqual(sum(m['role']=='system' for m in calls[-1]),1)
   self.assertTrue(any(m['content'].startswith('TOOL_RESULT') for m in calls[-1]))

 def test_local_snapshot_still_calculates(self):
  with tempfile.TemporaryDirectory() as temp:
   a=ChatAgent('http://localhost:42866/v1',Path(temp)/'log')
   self.assertEqual(len(a.engine.snapshot),30)
   self.assertAlmostEqual(a.dispatch('ticker_metrics',{'ticker':'0700.HK','window':60})['metrics']['Net profit margin']['value'],27.356495837097444)
   a.state['last_ranking_request']={'top_k':3,'weights':{'net_profit_margin':1},'filters':{'net_profit_margin':{'min':10}}}
   r=a.dispatch('rank_stocks',{'reuse_previous':True,'top_k':5});self.assertEqual(len(r['results']),5);self.assertEqual(r['filters'],{'net_profit_margin':{'min':10}})

 def test_market_history_external_symbol(self):
  from datetime import datetime,timezone
  values=[100+i/10 for i in range(260)]
  payload={'chart':{'result':[{'meta':{'symbol':'AAPL','currency':'USD','longName':'Apple','exchangeTimezoneName':'UTC'},'timestamp':[1700000000+i*86400 for i in range(260)],'indicators':{'adjclose':[{'adjclose':values}],'quote':[{'volume':[1000]*260}]}}],'error':None}}
  r=WebTools(lambda url:fixture_page(url,json.dumps(payload),'application/json')).market_history('AAPL',60)
  self.assertEqual(r['symbol'],'AAPL');self.assertEqual(len(r['chart']['dates']),61);self.assertTrue(r['sources']);self.assertNotIn('Fixed snapshot',str(r))
  payload['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'][4]=None
  with self.assertRaisesRegex(ValueError,'missing/invalid'):WebTools(lambda url:fixture_page(url,json.dumps(payload),'application/json')).market_history('AAPL')

 def test_exact_token_budget_drops_complete_old_turns(self):
  def model(*a,**kw):raise AssertionError('No inference needed')
  model.count_tokens=lambda messages,url:(20000 if any('OLD_CONTEXT' in m['content'] for m in messages) else 5000,16384)
  with tempfile.TemporaryDirectory() as temp:
   a=ChatAgent('http://localhost:42866/v1',Path(temp)/'log',call=model)
   a.messages += [{'role':'user','content':'older question'}, {'role':'assistant','content':'OLD_CONTEXT'}, {'role':'user','content':'Current Anthropic question'}]
   m=a._context();self.assertEqual(len(m),2);self.assertEqual(m[-1]['content'],'Current Anthropic question');self.assertEqual(m[0]['role'],'system')

 def test_current_page_can_be_compacted_without_losing_full_evidence(self):
  def model(*a,**kw):raise AssertionError('No inference needed')
  model.count_tokens=lambda messages,url:(5000 if any('context_compacted' in m['content'] for m in messages) else 20000,16384)
  with tempfile.TemporaryDirectory() as temp:
   a=ChatAgent('http://localhost:42866/v1',Path(temp)/'log',call=model)
   r={'kind':'webpage','text':'X'*6000};a.evidence=[dict(id='E1',tool='read_webpage',arguments={},result=r)]
   a.messages += [{'role':'user','content':'Read page'},{'role':'assistant','content':'{}'},{'role':'user','content':'TOOL_RESULT\n'+json.dumps({'id':'E1','result':r})}]
   m=a._context();self.assertEqual(len(json.loads(m[-1]['content'].split('\n',1)[1])['result']['text']),2400);self.assertEqual(len(a.evidence[0]['result']['text']),6000)

 def test_oversize_current_turn_fails_before_inference(self):
  def model(*a,**kw):raise AssertionError('No inference needed')
  model.count_tokens=lambda messages,url:(20000,16384)
  with tempfile.TemporaryDirectory() as temp:
   a=ChatAgent('http://localhost:42866/v1',Path(temp)/'log',call=model);a.messages.append({'role':'user','content':'question'})
   with self.assertRaisesRegex(RuntimeError,'cannot fit'):a._context()
   model.count_tokens=lambda messages,url:(15000,16384)
   self.assertEqual(len(a._context(reserved_output_tokens=0)),2)

 def test_worker_renders_network_sources(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/('a'*32+'.ask');atomic_json(path,{'session':'b'*32,'question':'Read company source'})
   n=[0]
   def factory(base,log):
    def model(*a,**kw):
     n[0]+=1
     return response({'tool':'read_webpage','arguments':{'url':'https://company.example/'}}) if n[0]==1 else response({'answer':'The company source was retrieved. [E1]'})
    agent=ChatAgent(base,log,call=model);agent.web=WebTools(lambda url:fixture_page(url,'<title>Company</title><p>'+'Primary source company evidence. '*20+'</p>'));return agent
   process(path,{},'http://localhost:42866/v1',factory)
   r=json.loads(path.with_suffix('.reply').read_text());self.assertNotIn('error',r);self.assertTrue(r['evidence'][0]['sources']);self.assertTrue((Path(temp)/('b'*32+'.state')).exists())

if __name__=='__main__':unittest.main()
