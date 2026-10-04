"""Controller integration with explicit fixtures; not real model capability evidence."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import pytest
from rsi.common import *
from rsi.catalog import catalog
from rsi.registry import Registry
from rsi.provider import Ollama
from rsi.sandbox import Result,Sandbox
from rsi.runtime import Runtime,STRATEGY_DRIVER,SOLUTION_DRIVER
from rsi.engine import Engine

BASELINE=Path(__file__).resolve().parents[2]/'rsi'/'strategies'/'baseline.py'
CANDIDATE=BASELINE.read_text()+'\n# fixture candidate; improves only the test provider, not a real model\n'
CANDIDATE2=CANDIDATE+'\n# fixture second generation\n'

class FixtureSandbox:
    """Only maps exact trusted test strings; never evals arbitrary candidate code."""
    def __init__(self):self.seen=[]
    def probe(self):return {'backend':'TEST_FIXTURE','identity':'not-a-real-sandbox'}
    def run(self,files,**kwargs):
        if kwargs.get('cancel'):kwargs['cancel']()
        self.seen.append(dict(files))
        if files['main.py']==STRATEGY_DRIVER:
            if files['strategy.py'] not in (BASELINE.read_text(),CANDIDATE,CANDIDATE2):return Result(1,'','unsupported fixture',0)
            payload=json.loads(files['input.json']);payload['fixture_candidate']=files['strategy.py']!=BASELINE.read_text();payload['fixture_level']=2 if files['strategy.py']==CANDIDATE2 else (1 if files['strategy.py']==CANDIDATE else 0)
            return Result(0,json.dumps({'context':json.dumps(payload)}),'',.001,backend='TEST_FIXTURE')
        assert files['main.py']==SOLUTION_DRIVER
        # Trusted fixture lookup; input never contains expected answers.
        source=files['solution.py'];known=next((t for t in catalog() if source in (t['reference'],t['files']['solution.py'])),None)
        if known is None:return Result(1,'','unknown fixture',.001)
        checks=json.loads(files['input.json']);assert all(set(c)=={'args'} for c in checks)
        outputs=[]
        for c in checks:
            case=next(x for x in known['public']+known['hidden'] if x['args']==c['args'])
            value=case['expected'] if source==known['reference'] else {'wrong':'fixture'}
            outputs.append({'ok':True,'value':value})
        return Result(0,json.dumps(outputs),'',.001,backend='TEST_FIXTURE')

class FixtureProvider:
    def __init__(self,registry,improve=True):self.registry=registry;self.improve=improve;self.requests=[]
    def probe(self):return {'provider':'TEST_FIXTURE','model':'not-a-real-model','digest':'fixture-v1'}
    def complete(self,messages,rid,seed=0):
        self.registry.check(rid);cid=self.registry.reserve(rid,100);self.registry.settle(cid,25,{'fixture':True})
        self.requests.append(messages);payload=json.loads(messages[-1]['content'])
        if payload['mode']=='propose':return {'hypothesis':'Fixture change for orchestration test only','strategy_source':CANDIDATE if payload['source']==BASELINE.read_text() else CANDIDATE2}
        if self.improve and payload['fixture_candidate'] and int(payload['task']['id'].split('-')[-1])<=2*payload['fixture_level']:
            task=next(t for t in catalog() if t['id']==payload['task']['id'])
            return {'actions':[{'tool':'write_file','path':'solution.py','sha256':payload['files']['solution.py']['sha256'],'content':task['reference']},{'tool':'finish'}]}
        return {'actions':[{'tool':'finish'}]}

@pytest.fixture
def fixture_engine(tmp_path):
    r=Registry(tmp_path);e=Engine(tmp_path,FixtureProvider(r),FixtureSandbox());e.init()
    # Small disjoint subset for pipeline tests; production pack has 60 tasks.
    tasks=[t for t in catalog() if int(t['id'].split('-')[-1])<=2]
    atomic_json(e.benchmark.path,tasks)
    return e

def test_complete_campaign_without_proof_fabrication(fixture_engine):
    e=fixture_engine;old=e.registry.active()['id']
    result=e.campaign(1)
    assert result['status']=='complete',result
    assert result['generations'][0]['status']=='accepted'
    assert result['pilot_capability_gain_confirmed']
    assert not result['actual_rsi_improvement_proven']
    assert e.registry.active()['id']==old
    aid=result['generations'][0]['candidate']
    activated=e.activate(aid)
    assert activated['status']=='complete',activated
    assert e.registry.active()['id']==aid
    assert e.registry.artifact(aid)['parent']==old
    assert e.registry.rollback()==old
    again=e.campaign(1)
    assert again['stop_reason']=='fresh_final_dataset_required'
    assert not again['generations']
    # No hidden expectations cross the sandbox boundary.
    for files in e.sandbox.seen:
        if files['main.py']==SOLUTION_DRIVER:
            assert all('expected' not in c for c in json.loads(files['input.json']))
    # Proposal only receives development evidence, not validation/final tasks.
    proposals=[json.loads(m[-1]['content']) for m in e.provider.requests if json.loads(m[-1]['content'])['mode']=='propose']
    assert all(r['task'].startswith('dev-') for p in proposals for r in p['evidence'])

def test_no_gain_keeps_active(fixture_engine):
    e=fixture_engine;e.provider.improve=False;old=e.registry.active()['id']
    result=e.campaign(1)
    assert result['generations'][0]['status']=='rejected_development'
    assert e.registry.active()['id']==old
    assert 'pilot_capability_gain_confirmed' not in result

def test_budget_stops_without_promoting(fixture_engine):
    e=fixture_engine;e.cfg['max_calls']=1;old=e.registry.active()['id']
    result=e.campaign(1)
    assert result['status']=='budget_exhausted'
    assert result['usage']['n']==1
    assert e.registry.active()['id']==old

def test_automatic_canary_and_holdout_stop(fixture_engine):
    e=fixture_engine;e.cfg['auto_promote']=True
    result=e.campaign(2)
    assert result['status']=='complete',result
    assert result['generations'][0]['status']=='promoted'
    assert result['stop_reason']=='fresh_final_dataset_required'
    assert e.registry.active()['id']==result['generations'][0]['candidate']

def test_failed_canary_rolls_back(fixture_engine,monkeypatch):
    e=fixture_engine;old=e.registry.active()['id'];result=e.campaign(1)
    aid=result['generations'][0]['candidate'];original=e.runtime.solve
    counter=[0]
    def fail_after_activation(*args,**kwargs):
        counter[0]+=1
        if counter[0]==2:raise RSIError('canary failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(e.runtime,'solve',fail_after_activation)
    result=e.activate(aid)
    assert result['status']=='failed'
    assert e.registry.active()['id']==old

def test_guarded_tools(fixture_engine,tmp_path):
    e=fixture_engine;t=catalog()[0];root=tmp_path/'task';root.mkdir();(root/'solution.py').write_text(t['files']['solution.py'])
    with pytest.raises(RSIError):e.runtime.tool(root,t,{'tool':'write_file','path':'../config.json','sha256':'x','content':'bad'},'unused')
    with pytest.raises(RSIError,match='Stale'):e.runtime.tool(root,t,{'tool':'write_file','path':'solution.py','sha256':'wrong','content':'x=1'},'unused')
    with pytest.raises(RSIError):e.runtime.tool(root,t,{'tool':'shell','command':'echo unsafe'},'unused')

class Handler(BaseHTTPRequestHandler):
    mode='normal'
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'models':[{'name':'fixture:latest','digest':'abc'}]}).encode())
    def do_POST(self):
        size=int(self.headers['Content-Length']);body=json.loads(self.rfile.read(size))
        assert body['stream'] is False and body['format']=='json'
        if type(self).mode=='slow':time.sleep(2)
        value={'done':True,'message':{'content':json.dumps({'actions':[{'tool':'finish'}]})},'prompt_eval_count':10,'eval_count':5}
        self.send_response(200);self.end_headers()
        try:self.wfile.write(json.dumps(value).encode())
        except BrokenPipeError:pass

@pytest.fixture
def http_provider(tmp_path):
    Handler.mode='normal';server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    cfg=dict(DEFAULTS,model='fixture',ollama_url=f'http://127.0.0.1:{server.server_port}')
    registry=Registry(tmp_path);rid=registry.new_run('fixture-http',cfg)
    try:yield Ollama(cfg,registry),rid,registry
    finally:server.shutdown();server.server_close();thread.join()

def test_actual_http_adapter_contract(http_provider):
    provider,rid,registry=http_provider
    result=provider.complete([{'role':'user','content':'hello'}],rid)
    assert result['actions'][0]['tool']=='finish'
    assert registry.usage(rid)['actual']==15

def test_cancel_closes_transport(http_provider):
    provider,rid,registry=http_provider;Handler.mode='slow'
    timer=threading.Timer(.3,lambda:registry.stop(rid));timer.start();started=time.monotonic()
    with pytest.raises(Cancelled):provider.complete([{'role':'user','content':'hello'}],rid)
    timer.join();assert time.monotonic()-started<1.5
    assert registry.usage(rid)['charged']>0

def test_no_unsafe_sandbox_fallback(monkeypatch):
    monkeypatch.setattr('rsi.sandbox.shutil.which',lambda x:None)
    with pytest.raises(Unavailable):Sandbox(DEFAULTS).run({'main.py':'print(1)'})

@pytest.mark.parametrize('url',['https://example.com','http://localhost@evil.test','http://127.0.0.1/redirect','file:///tmp/a'])
def test_provider_loopback_only(tmp_path,url):
    with pytest.raises(RSIError):Ollama(dict(DEFAULTS,ollama_url=url),Registry(tmp_path))


def test_recursive_lineage_on_fresh_fixture_sets(fixture_engine):
    e=fixture_engine;e.cfg['auto_promote']=True
    first=e.campaign(1)
    assert first['generations'][0]['status']=='promoted'
    parent=e.registry.active()['id']
    new_tasks=[t for t in catalog() if 3<=int(t['id'].split('-')[-1])<=4]
    atomic_json(e.benchmark.path,new_tasks)
    second=e.campaign(1)
    assert second['status']=='complete',second
    assert second['generations'][0]['status']=='promoted'
    assert second['generations'][0]['parent']==parent
    assert e.registry.artifact(e.registry.active()['id'])['parent']==parent
    assert not second['actual_rsi_improvement_proven']


def test_fake_pass_log_is_not_a_result(fixture_engine):
    e=fixture_engine
    class FakeOutput:
        def run(self,*args,**kwargs):return Result(0,'{"passed": true}','','.001')
    e.runtime.sandbox=FakeOutput()
    rid=e.registry.new_run('test',e.cfg)
    result=e.runtime.evaluate_code({'solution.py':'irrelevant'},[{'args':[],'expected':5}],rid)
    assert not result['passed']


def test_supervisor_timeout(tmp_path):
    import sys
    box=Sandbox(DEFAULTS)
    result=box._process([sys.executable,'-I','-c','import time; time.sleep(5)'],tmp_path,.1)
    assert result.timed_out and result.returncode!=0
    assert result.elapsed<2
