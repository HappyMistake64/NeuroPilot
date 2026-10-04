"""App-server protocol fixtures; none of these tests call an actual model."""
import json
import time

import pytest

from rsi import codex_connection as codex
from rsi.common import DEFAULTS, RSIError, Unavailable, atomic_json
from rsi.engine import Engine


class FakeClient:
    account_type='chatgpt'
    mode='ok'
    requests=[]
    def __init__(self,timeout=120,check=None):
        self.events=[]
        self.workspace=type('Workspace',(),{'name':'/tmp/isolated-codex-fixture'})()
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def account(self):
        return {'auth_type':self.account_type,'signed_in':self.account_type=='chatgpt','model_inference_verified':False}
    def models(self): return [{'id':'fixture-model','default':True}]
    def rpc(self,method,params):
        self.requests.append((method,params))
        if method=='config/read': return {'config':{'mcp_servers':{'fixture':{'enabled':True}}}}
        if method=='thread/start':
            return {'thread':{'id':'thread-test'},'model':'fixture-model',
                    'modelProvider':'other' if self.mode=='provider_changed' else 'openai',
                    'sandbox':{'type':'readOnly'},'instructionSources':[]}
        if method=='turn/start':
            expected=json.loads(params['input'][0]['text'].split(': ',1)[1])
            if self.mode=='wrong_nonce': expected['nonce']='wrong'
            if self.mode=='tool': self.events.append({'method':'item/started','params':{'threadId':'thread-test','item':{'type':'commandExecution'}}})
            if self.mode!='unknown_usage':
                self.events.append({'method':'thread/tokenUsage/updated','params':{'threadId':'thread-test','tokenUsage':{'last':{'inputTokens':20,'outputTokens':5}}}})
            self.events.extend([
                {'method':'item/completed','params':{'threadId':'thread-test','item':{'type':'agentMessage','text':json.dumps(expected)}}},
                {'method':'turn/completed','params':{'threadId':'thread-test','turn':{'id':'turn-test',
                    'status':'failed' if self.mode=='unauthorized' else 'completed','error':{'codexErrorInfo':'unauthorized','message':'never-log-secret'}}}},
            ])
            return {'turn':{'id':'turn-test'}}
        raise AssertionError(method)
    def receive(self): raise Unavailable('fixture stream ended')


@pytest.fixture
def client(monkeypatch):
    FakeClient.account_type='chatgpt';FakeClient.mode='ok';FakeClient.requests=[]
    monkeypatch.setattr(codex,'AppServer',FakeClient)
    return FakeClient


def test_actual_completion_required_and_request_has_no_environment_tools(client,tmp_path):
    engine=Engine(tmp_path/'state')
    result=codex.connection_check(engine)
    assert result['model_inference_verified'] is True
    assert result['response']['connection']=='ok' and len(result['response']['nonce'])==32
    assert result['usage']['actual']==25 and result['usage']['n']==1
    assert result['underlying_model_calls'] is None and result['budget_unit']=='codex_turn'
    assert result['rsi_experiments_supported'] is False
    thread=next(params for method,params in client.requests if method=='thread/start')
    assert thread['environments']==[] and thread['dynamicTools']==[]
    assert thread['ephemeral'] and thread['sandbox']=='read-only'
    assert thread['config']['mcp_servers."fixture".enabled'] is False
    assert engine.cfg['provider']=='ollama' and engine.registry.check_chain()


@pytest.mark.parametrize('mode,status', [('unauthorized','blocked'),('wrong_nonce','failed'),('tool','failed'),('provider_changed','failed')])
def test_failure_never_counts_as_inference(client,tmp_path,mode,status):
    client.mode=mode
    engine=Engine(tmp_path/'state');result=codex.connection_check(engine)
    assert result['status']==status and result['model_inference_verified'] is False
    assert 'never-log-secret' not in json.dumps(result)
    if mode=='unauthorized':
        assert result['error_code']=='unauthorized' and result['usage']['actual']==25


@pytest.mark.parametrize('kind',[None,'apiKey','amazonBedrock'])
def test_rejects_non_chatgpt_auth_before_turn(client,tmp_path,kind):
    client.account_type=kind
    result=codex.connection_check(Engine(tmp_path/'state'))
    assert result['status']=='blocked' and result['turns_submitted']==0
    assert not client.requests


def test_no_model_fallback(client,tmp_path):
    result=codex.connection_check(Engine(tmp_path/'state'),'not-in-catalog')
    assert result['status']=='blocked' and result['turns_submitted']==0
    assert not client.requests


def test_unknown_usage_stays_charged(client,tmp_path):
    client.mode='unknown_usage'
    result=codex.connection_check(Engine(tmp_path/'state'))
    assert result['usage']['unknown']==1
    assert result['usage']['charged']==DEFAULTS['context_tokens']+DEFAULTS['output_tokens']


def test_budget_refuses_turn_before_submission(client,tmp_path):
    state=tmp_path/'state';atomic_json(state/'config.json',dict(DEFAULTS,max_tokens=1))
    result=codex.connection_check(Engine(state))
    assert result['status']=='budget_exhausted' and result['turns_submitted']==0
    assert not any(method=='turn/start' for method,_ in client.requests)


def test_appserver_deadline_applies_even_with_buffered_events():
    server=codex.AppServer();server.deadline=0;server.buffer=b'{}\n'
    try:
        with pytest.raises(Unavailable,match='timed out'): server.receive()
    finally: server.selector.close()


def test_appserver_rejects_server_tool_requests():
    server=codex.AppServer();sent=[];server.send=sent.append
    server.buffer=b'{"id":17,"method":"item/tool/call","params":{}}\n'
    try:
        with pytest.raises(RSIError,match='unsupported client action'): server.receive()
        assert sent[0]['id']==17 and 'error' in sent[0]
    finally: server.selector.close()


@pytest.mark.parametrize('exit_code',[0,1])
def test_device_login_delegates_to_official_cli(client,monkeypatch,tmp_path,exit_code):
    import sys
    executable=tmp_path/'codex-fixture'
    args_file=tmp_path/'arguments.json'
    executable.write_text('#!'+sys.executable+'\nimport sys,json\n'
        +'open('+repr(str(args_file))+',"w").write(json.dumps(sys.argv[1:]))\n'
        +'raise SystemExit('+str(exit_code)+')\n')
    executable.chmod(0o700)
    monkeypatch.setattr(codex.shutil,'which',lambda _:str(executable))
    if exit_code:
        with pytest.raises(Unavailable,match='device login failed'): codex.login()
    else:
        result=codex.login()
        assert result['signed_in'] and result['model_inference_verified'] is False
    assert json.loads(args_file.read_text())==['login','--device-auth']


def test_appserver_timeout_terminates_process_group(monkeypatch,tmp_path):
    import os
    import sys
    import textwrap
    executable=tmp_path/'fake-codex'
    executable.write_text('#!'+sys.executable+'\n'+textwrap.dedent('''
        import sys,json,time
        for line in sys.stdin:
            request=json.loads(line)
            if request.get('method')=='initialize':
                print(json.dumps({'id':request['id'],'result':{}}),flush=True)
            else:
                time.sleep(60)
    '''))
    executable.chmod(0o700)
    monkeypatch.setattr(codex.shutil,'which',lambda _:str(executable))
    server=codex.AppServer(timeout=.2)
    with pytest.raises(Unavailable,match='timed out'):
        with server:
            server.rpc('account/read',{'refreshToken':False})
    assert server.process.poll() is not None
    with pytest.raises(ProcessLookupError): os.killpg(server.process.pid,0)


def test_account_status_is_never_inference(client):
    result=codex.status()
    assert result['signed_in'] and result['model_inference_verified'] is False
    assert result['models']==[{'id':'fixture-model','default':True}]
