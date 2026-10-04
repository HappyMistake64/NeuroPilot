"""Accounting and isolation regressions; fake upstream, no credentials/network."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from rsi.codex_gateway import Gateway, parse_stream
from rsi.codex_provider import profile
from rsi.common import DEFAULTS, BudgetExceeded, Cancelled, RSIError, Unavailable
from rsi.registry import Registry


@pytest.fixture
def gateway(tmp_path,monkeypatch):
    cfg=dict(DEFAULTS,max_calls=1,max_tokens=30000)
    registry=Registry(tmp_path);rid=registry.new_run('fixture',cfg)
    gateway=Gateway(cfg,registry,rid,'fixture-model','fixture-account')
    gateway.sent=[]
    def upstream(body,headers):
        gateway.sent.append((body,headers))
        return {'ok':True,'raw':b'fixture','response':{'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'{}'}]}],'usage':{'input_tokens':20,'output_tokens':5}}}
    monkeypatch.setattr(gateway,'_exchange',upstream)
    return gateway


def request_body(**extra):
    return dict(model='fixture-model',stream=True,store=False,input=[{'role':'user','content':'fixture'}],**extra)


def test_each_retry_reserves_before_dispatch_and_tools_are_stripped(gateway):
    first=gateway.forward(request_body(tools=[{'type':'shell'}],tool_choice='auto'),{'Authorization':'Bearer secret','Cookie':'secret'})
    assert first['ok'] and gateway.registry.usage(gateway.rid)['actual']==25
    second=gateway.forward(request_body(),{})
    assert not second['ok'] and isinstance(gateway.failure,BudgetExceeded)
    assert len(gateway.sent)==1 and gateway.forwarded==1
    body,headers=gateway.sent[0]
    assert body['tools']==[] and body['parallel_tool_calls'] is False and 'tool_choice' not in body
    assert 'Cookie' not in headers
    with gateway.registry.connect() as conn:
        events=''.join(row[0] for row in conn.execute('SELECT payload FROM events'))
    assert 'secret' not in events and gateway.registry.check_chain()


def test_upstream_failure_retains_reservation_and_retry_cannot_bypass_limit(gateway,monkeypatch):
    monkeypatch.setattr(gateway,'_exchange',lambda *_:{'ok':False,'status':503})
    assert not gateway.forward(request_body(),{})['ok']
    usage=gateway.registry.usage(gateway.rid)
    assert usage['n']==1 and usage['unknown']==1 and usage['charged']==10240
    assert not gateway.forward(request_body(),{})['ok']
    assert isinstance(gateway.failure,BudgetExceeded)


def test_response_overrun_is_charged_and_stops(gateway,monkeypatch):
    monkeypatch.setattr(gateway,'_exchange',lambda *_:{'ok':True,'raw':b'x','response':{'output':[],'usage':{'input_tokens':30001,'output_tokens':1}}})
    assert not gateway.forward(request_body(),{})['ok']
    assert isinstance(gateway.failure,BudgetExceeded)
    assert gateway.registry.usage(gateway.rid)['charged']==30002


def test_unknown_usage_keeps_reservation(gateway,monkeypatch):
    monkeypatch.setattr(gateway,'_exchange',lambda *_:{'ok':True,'raw':b'x','response':{'output':[]}})
    assert gateway.forward(request_body(),{})['ok']
    assert gateway.registry.usage(gateway.rid)['unknown']==1
    assert gateway.registry.usage(gateway.rid)['charged']==10240


def test_cancel_before_dispatch(gateway):
    gateway.registry.stop(gateway.rid)
    assert not gateway.forward(request_body(),{})['ok']
    assert isinstance(gateway.failure,Cancelled) and not gateway.sent


@pytest.mark.parametrize('change',[{'model':'fallback'},{'store':True},{'stream':False},{'conversation':'old'}, {'input':[{'type':'function_call_output'}]}])
def test_invalid_requests_never_dispatch(gateway,change):
    body=request_body();body.update(change)
    assert not gateway.forward(body,{})['ok']
    assert not gateway.sent and gateway.registry.usage(gateway.rid)['n']==0


@pytest.mark.parametrize('headers,code',[({'Origin':'https://other.test'},400),({'Authorization':'wrong'},403),({'ChatGPT-Account-Id':'other'},403),({'Host':'other.test'},404)])
def test_loopback_endpoint_rejects_untrusted_request(gateway,headers,code):
    with gateway:
        merged={'Authorization':'Bearer fixture','ChatGPT-Account-Id':'fixture-account',**headers}
        req=Request(gateway.url+'/responses',data=json.dumps(request_body()).encode(),headers=merged)
        with pytest.raises(HTTPError) as error:urlopen(req,timeout=2)
        assert error.value.code==code
        assert not gateway.sent


def sse(*events):
    return ''.join('data: '+json.dumps(event)+'\n\n' for event in events).encode()


def test_terminal_empty_output_uses_completed_items():
    item={'type':'message','role':'assistant','content':[{'type':'output_text','text':'{}'}]}
    raw=sse({'type':'response.output_item.done','output_index':0,'item':item},
            {'type':'response.completed','response':{'status':'completed','output':[],'usage':{'input_tokens':1,'output_tokens':2}}})
    assert parse_stream(raw)['output']==[item]


@pytest.mark.parametrize('raw',[sse({'type':'response.output_item.done','output_index':0,'item':{}}),sse({'type':'response.completed','response':{'status':'completed','output':[]}})])
def test_partial_or_empty_completion_rejected(raw):
    with pytest.raises(RSIError):parse_stream(raw)


@pytest.mark.parametrize('override',['EU_RESIDENCY','unknown',None])
def test_managed_routing_never_bypassed(override):
    class Client:
        def rpc(self,*_):return {'account':{'type':'chatgpt','email':'fixture@example.invalid'},'workspaceRouting':{'chatgptAccountId':'fixture','backendOrigin':'https://chatgpt.com','accountRoutingOverride':override}}
    with pytest.raises(Unavailable,match='routing'):profile(Client())


def test_web_codex_selection_is_explicit_and_never_claims_inference(tmp_path,monkeypatch):
    import server
    from rsi import codex_connection,codex_provider
    monkeypatch.setenv('NEUROPILOT_RSI_STATE',str(tmp_path/'state'))
    monkeypatch.setattr(codex_connection,'status',lambda:{'signed_in':True,'models':[{'id':'fixture-model'}],'model_inference_verified':False})
    def probe(self):
        if self.cfg['codex_model']!='fixture-model':raise Unavailable('Invalid catalog model')
        return {'provider':'codex_chatgpt'}
    monkeypatch.setattr(codex_provider.Codex,'probe',probe)
    client=server.app.test_client()
    response=client.post('/rsi/api/codex/status',json={})
    assert response.status_code==200 and response.json['model_inference_verified'] is False
    assert response.headers['Cache-Control']=='no-store'
    assert client.post('/rsi/api/codex/configure',json={'model':'invented'}).status_code==400
    assert client.post('/rsi/api/codex/configure',json={'model':'fixture-model'},headers={'Origin':'https://other.test'}).status_code==403
    assert client.post('/rsi/api/codex/configure',json={'model':'fixture-model'}).status_code==200
    assert client.get('/rsi/api/status').json['provider']=={'kind':'codex','model':'fixture-model'}

def test_native_tool_event_rejected_even_if_terminal_output_looks_safe():
    raw=sse({'type':'response.output_item.added','item':{'type':'function_call'}},
            {'type':'response.completed','response':{'status':'completed','output':[{'type':'message'}]}})
    with pytest.raises(RSIError,match='tool output'):parse_stream(raw)


def test_provider_uses_budgeted_custom_route_and_disables_tools(gateway,monkeypatch):
    from rsi import codex_provider
    requests=[]
    class Client:
        def __init__(self,**kw):
            self.workspace=type('Workspace',(),{'name':'/tmp/fixture'})()
            self.events=[]
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def models(self):return [{'id':'fixture-model'}]
        def rpc(self,method,params):
            requests.append((method,params))
            if method=='account/read':return {'account':{'type':'chatgpt','email':'fixture@example.invalid'},'workspaceRouting':{'chatgptAccountId':'fixture-account','backendOrigin':'https://chatgpt.com','accountRoutingOverride':'NO_CONSTRAINT'}}
            if method=='config/read':return {'config':{'mcp_servers':{'fixture':{}}}}
            if method=='thread/start':return {'thread':{'id':'t'},'model':'fixture-model','modelProvider':codex_provider.PROVIDER,'sandbox':{'type':'readOnly'},'instructionSources':[]}
            if method=='turn/start':
                gateway.forward(request_body(),{})
                self.events=[{'method':'turn/completed','params':{'threadId':'t','turn':{'id':'turn','status':'completed'}}}]
                return {'turn':{'id':'turn'}}
            raise AssertionError(method)
    monkeypatch.setattr(codex_provider,'AppServer',Client)
    monkeypatch.setattr(codex_provider,'Gateway',lambda *args:gateway)
    provider=codex_provider.Codex(dict(gateway.cfg,codex_model='fixture-model'),gateway.registry)
    assert provider.complete([{'role':'user','content':'fixture'}],gateway.rid)=={}
    thread=next(p for method,p in requests if method=='thread/start')
    assert thread['environments']==[] and thread['dynamicTools']==[] and thread['selectedCapabilityRoots']==[]
    assert thread['allowProviderModelFallback'] is False and thread['ephemeral'] is True
    assert thread['config']['mcp_servers."fixture".enabled'] is False
    definition=thread['config']['model_providers.'+codex_provider.PROVIDER]
    assert definition['requires_openai_auth'] is True and definition['supports_websockets'] is False
    assert definition['request_max_retries']==0 and definition['base_url'].startswith('http://127.0.0.1:')
    assert gateway.registry.usage(gateway.rid)['n']==1


def slow_exchange(body,headers,timeout,connection):
    import time
    time.sleep(30)


@pytest.mark.parametrize('cancel',[False,True])
def test_upstream_worker_is_killed_on_timeout_or_stop(tmp_path,monkeypatch,cancel):
    import multiprocessing
    import threading
    from rsi import codex_gateway
    cfg=dict(DEFAULTS,model_timeout=.3)
    registry=Registry(tmp_path);rid=registry.new_run('fixture',cfg)
    gateway=Gateway(cfg,registry,rid,'fixture-model','fixture-account')
    monkeypatch.setattr(codex_gateway,'exchange',slow_exchange)
    before={p.pid for p in multiprocessing.active_children()}
    timer=None
    if cancel:
        cfg['model_timeout']=5
        timer=threading.Timer(.2,lambda:registry.stop(rid));timer.start()
    try:
        assert not gateway.forward(request_body(),{})['ok']
        assert isinstance(gateway.failure,Cancelled if cancel else Unavailable)
        assert registry.usage(rid)['n']==1 and registry.usage(rid)['unknown']==1
        assert {p.pid for p in multiprocessing.active_children()}<=before
    finally:
        if timer:timer.join()
