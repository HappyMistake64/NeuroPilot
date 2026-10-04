"""OAuth, SSE and quota contract tests; fixtures are NOT real OpenAI inference."""
import io
import json
import multiprocessing
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from rsi import openai_auth as auth
from rsi import openai_provider as provider
from rsi.common import DEFAULTS, RSIError, Unavailable, BudgetExceeded, Cancelled, atomic_json, load_config
from rsi.registry import Registry
from rsi.engine import Engine

@pytest.fixture
def accounts(tmp_path,monkeypatch):
    monkeypatch.setenv('NEUROPILOT_OPENAI_AUTH_DIR',str(tmp_path/'auth'))
    return auth.Accounts()

@pytest.fixture(scope='module')
def signing_key(): return rsa.generate_private_key(public_exponent=65537,key_size=2048)

def token_response(identity='signed.id.token',**changes):
    return dict(access_token='secret-access',refresh_token='secret-refresh',id_token=identity,
                token_type='Bearer',expires_in=3600,scope=auth.SCOPE,**changes)

def signed(signing_key,expected_nonce,cid='oaiapp_test',**changes):
    claims=dict(sub='user-test',iss=auth.ISSUER,aud=cid,iat=int(time.time()),exp=int(time.time())+3600,nonce=expected_nonce,email='test@example.com')
    claims.update(changes)
    return jwt.encode(claims,signing_key,algorithm='RS256',headers={'kid':'key-1'})

def mock_service(monkeypatch,key,tokens):
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));public['kid']='key-1'
    calls=[]
    def request(url,form=None,**kwargs):
        calls.append((url,form,kwargs))
        if url.endswith('openid-configuration'):return {'issuer':auth.ISSUER,'jwks_uri':auth.ISSUER+'/.well-known/jwks.json','revocation_endpoint':auth.ISSUER+'/revoke'}
        if url.endswith('jwks.json'):return {'keys':[public]}
        if url.endswith('/revoke'):return {}
        assert url==auth.TOKEN
        return tokens() if callable(tokens) else tokens
    monkeypatch.setattr(auth,'request_json',request)
    return calls

def connect(accounts,monkeypatch,key,cid='oaiapp_test'):
    pending,url=accounts.prepare('http://127.0.0.1:54321/auth/callback')
    response=token_response(signed(key,pending['nonce'],cid))
    calls=mock_service(monkeypatch,key,response)
    accounts.accept(pending,{'state':pending['state'],'code':'auth-code','client_id':cid})
    return pending,url,calls

def test_pkce_registration_and_atomic_credentials(accounts,monkeypatch,signing_key):
    pending,url,calls=connect(accounts,monkeypatch,signing_key)
    params=parse_qs(urlsplit(url).query)
    assert params['client_id']==['dynamic_agent_client'] and params['agent_name_hint']==['NeuroPilot']
    assert params['code_challenge_method']==['S256'] and len(params['code_challenge'][0])==43
    assert params['resource']==[auth.RESOURCE]
    assert calls[0][1]['client_id']=='oaiapp_test'
    assert calls[0][1]['redirect_uri']==pending['redirect_uri']
    assert calls[0][1]['code_verifier']==pending['verifier']
    assert oct(accounts.path.stat().st_mode&0o777)=='0o600'
    assert oct(accounts.root.stat().st_mode&0o777)=='0o700'
    status=accounts.status();assert status['active']=='oaiapp_test'
    assert 'secret-' not in json.dumps(status) and 'id_token' not in json.dumps(status)
    assert accounts.credentials()[0]=='secret-access'
    again,url=accounts.prepare(pending['redirect_uri'],'oaiapp_test')
    params2=parse_qs(urlsplit(url).query)
    assert params2['ext_agent_host_id']==params['ext_agent_host_id']
    assert params2['client_id']==['oaiapp_test'] and 'agent_name_hint' not in params2
    assert again['state']!=pending['state'] and again['verifier']!=pending['verifier']

@pytest.mark.parametrize('change',[{'iss':'https://evil.example'},{'aud':'another-client'},{'exp':1},{'nonce':'wrong'},{'sub':''}])
def test_jwt_rejects_bad_claims(accounts,monkeypatch,signing_key,change):
    pending,_=accounts.prepare('http://127.0.0.1:1234/auth/callback')
    mock_service(monkeypatch,signing_key,token_response(signed(signing_key,pending['nonce'],**change)))
    with pytest.raises(RSIError):accounts.accept(pending,{'state':pending['state'],'code':'x','client_id':'oaiapp_test'})
    assert accounts.status()['active'] is None

def test_bad_signature_and_unsafe_algorithm(monkeypatch,signing_key):
    mock_service(monkeypatch,signing_key,{})
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with pytest.raises(RSIError):auth.validate_identity(signed(other,'n'),'oaiapp_test','n')
    with pytest.raises(RSIError):auth.validate_identity(jwt.encode({'sub':'x'},'x'*32,algorithm='HS256'),'oaiapp_test','n')

@pytest.mark.parametrize('params',[{'state':'wrong','code':'x','client_id':'oaiapp_test'}, {'error':'access_denied'}, {'code':'x'}, {'code':'x','client_id':'dynamic_agent_client'}])
def test_callback_invalid_before_exchange(accounts,monkeypatch,params):
    pending,_=accounts.prepare('http://127.0.0.1:1234/auth/callback')
    monkeypatch.setattr(auth,'request_json',lambda *a,**k:pytest.fail('must not exchange'))
    with pytest.raises(RSIError):accounts.accept(pending,dict(state=pending['state'],**params) if 'state' not in params else params)

def test_expired_attempt(accounts,monkeypatch):
    pending,_=accounts.prepare('http://127.0.0.1:1234/auth/callback');pending['expires']=0
    monkeypatch.setattr(auth,'request_json',lambda *a,**k:pytest.fail('expired exchange'))
    with pytest.raises(RSIError):accounts.accept(pending,{'state':pending['state'],'code':'x','client_id':'oaiapp_test'})

def test_plan_permission_and_registration_retained(accounts,monkeypatch,signing_key):
    pending,_=accounts.prepare('http://127.0.0.1:1234/auth/callback')
    tokens=token_response(signed(signing_key,pending['nonce']));tokens['scope']='openid email'
    mock_service(monkeypatch,signing_key,tokens)
    with pytest.raises(Unavailable):accounts.accept(pending,{'state':pending['state'],'code':'x','client_id':'oaiapp_test'})
    assert accounts.status()['active'] is None
    assert accounts.status()['accounts'][0]['id']=='oaiapp_test'
    assert 'secret-access' not in accounts.path.read_text()

def test_account_identity_and_registration_cannot_change(accounts,monkeypatch,signing_key):
    connect(accounts,monkeypatch,signing_key)
    pending,_=accounts.prepare('http://127.0.0.1:1234/auth/callback','oaiapp_test')
    mock_service(monkeypatch,signing_key,token_response(signed(signing_key,pending['nonce'],sub='other')))
    with pytest.raises(RSIError):accounts.accept(pending,{'state':pending['state'],'code':'x','client_id':'oaiapp_other'})
    with pytest.raises(RSIError):accounts.accept(pending,{'state':pending['state'],'code':'x'})
    assert json.loads(accounts.path.read_text())['accounts']['oaiapp_test']['subject']=='user-test'

def test_serialized_refresh_rotation(accounts,monkeypatch,signing_key):
    connect(accounts,monkeypatch,signing_key)
    data=json.loads(accounts.path.read_text());data['accounts']['oaiapp_test']['expires_at']=0;accounts._save(data)
    tokens=token_response();tokens.pop('id_token');tokens['refresh_token']='rotated-refresh';tokens['access_token']='rotated-access'
    calls=mock_service(monkeypatch,signing_key,tokens)
    with ThreadPoolExecutor(max_workers=4) as pool: outputs=list(pool.map(lambda _:accounts.credentials(),range(4)))
    assert len(calls)==1 and all(x[0]=='rotated-access' for x in outputs)
    assert calls[0][1]['refresh_token']=='secret-refresh' and 'scope' not in calls[0][1]
    assert json.loads(accounts.path.read_text())['accounts']['oaiapp_test']['refresh_token']=='rotated-refresh'

def test_invalid_grant_clears_tokens_retains_account(accounts,monkeypatch,signing_key):
    connect(accounts,monkeypatch,signing_key)
    data=json.loads(accounts.path.read_text());data['accounts']['oaiapp_test']['expires_at']=0;accounts._save(data)
    def fail(*a,**k):raise auth.ServiceError('invalid_grant')
    monkeypatch.setattr(auth,'request_json',fail)
    with pytest.raises(Unavailable):accounts.credentials()
    assert 'secret-' not in accounts.path.read_text()
    assert accounts.status()['accounts'][0]['id']=='oaiapp_test'

@pytest.mark.parametrize('remote',[True,False])
def test_logout_revocation_and_no_local_tokens(accounts,monkeypatch,signing_key,remote):
    connect(accounts,monkeypatch,signing_key)
    if not remote:
        def fail(*a,**k):raise auth.ServiceError()
        monkeypatch.setattr(auth,'request_json',fail)
    result=accounts.logout()
    assert result['remote_revocation_confirmed']==remote
    assert 'secret-' not in accounts.path.read_text() and 'id_token' not in accounts.path.read_text()
    assert accounts.status()['active'] is None
    assert accounts.status()['accounts'][0]['id']=='oaiapp_test'

def test_real_loopback_listener_wrong_state_then_success(accounts,monkeypatch,signing_key):
    login=auth.Login(accounts)
    calls=mock_service(monkeypatch,signing_key,token_response(signed(signing_key,login.pending['nonce'])))
    base=login.pending['redirect_uri']
    try:
        with pytest.raises(HTTPError):urlopen(base+'?'+urlencode({'state':'wrong'}),timeout=2)
        assert not login.done.is_set() and not calls
        with urlopen(base+'?'+urlencode({'state':login.pending['state'],'code':'x','client_id':'oaiapp_test'}),timeout=2) as response:
            assert response.status==200 and response.headers['Cache-Control']=='no-store'
        assert login.done.wait(1) and login.result['status']=='connected'
        assert login.consumed
    finally:login.cancel()

def event(kind='response.completed',response=None):
    data={'type':kind,'response':response or completion()}
    return ('data: '+json.dumps(data)+'\n\n').encode()

def completion(text='{"connection":"ok"}',**changes):
    return dict(status='completed',model='fixture-model',usage={'input_tokens':20,'output_tokens':5},
                output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':text}]}],**changes)

def test_completed_sse_only():
    assert provider.completed_response(io.BytesIO(event()))['status']=='completed'
    with pytest.raises(Unavailable):provider.completed_response(io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'))
    with pytest.raises(RSIError):provider.completed_response(io.BytesIO(b'x'*1_000_001))

@pytest.mark.parametrize('kind',['response.failed','response.incomplete','error'])
def test_terminal_failure_not_success(kind):
    with pytest.raises(Unavailable):provider.completed_response(io.BytesIO(event(kind,{'error':{'code':'subscription_sharing_usage_limit_exceeded'}})))

class FakeAccounts:
    def credentials(self):return 'never-log-this-token','account-fingerprint'

@pytest.fixture
def model(tmp_path,monkeypatch):
    cfg=dict(DEFAULTS,provider='chatgpt',openai_model='fixture-model')
    registry=Registry(tmp_path/'state');model=provider.ChatGPT(cfg,registry,FakeAccounts())
    monkeypatch.setattr(provider,'request_json',lambda *a,**k:{'models':[{'slug':'fixture-model','visibility':'list','display_name':'Fixture'}]})
    return model,registry,registry.new_run('test',cfg)

def test_official_request_roles_no_tools_keys_or_unsupported_fields(model,monkeypatch):
    m,r,rid=model;seen=[]
    def chat(body,run):seen.append(body);return completion()
    monkeypatch.setattr(m,'_chat',chat)
    monkeypatch.setenv('OPENAI_API_KEY','must-not-be-used')
    assert m.complete([{'role':'system','content':'JSON only'},{'role':'user','content':'Hello'}],rid,42)=={'connection':'ok'}
    assert seen[0]=={'model':'fixture-model','store':False,'stream':True,'tools':[],
                     'input':[{'role':'developer','content':'JSON only'},{'role':'user','content':'Hello'}]}
    assert r.usage(rid)['actual']==25 and r.check_chain()
    with r.connect() as c:logs=''.join(row[0] for row in c.execute('SELECT payload FROM events'))
    assert 'never-log-this-token' not in logs and 'must-not-be-used' not in logs
    assert 'seed_applied":false' in logs

@pytest.mark.parametrize('usage',[{}, {'input_tokens':True,'output_tokens':1}])
def test_unknown_usage_is_not_free(model,monkeypatch,usage):
    m,r,rid=model;response=completion();response['usage']=usage
    monkeypatch.setattr(m,'_chat',lambda *args:response)
    m.complete([{'role':'user','content':'x'}],rid)
    assert r.usage(rid)['unknown']==1 and r.usage(rid)['charged']==DEFAULTS['context_tokens']+DEFAULTS['output_tokens']

def test_usage_survives_bad_json_and_tools_never_execute(model,monkeypatch,tmp_path):
    m,r,rid=model
    monkeypatch.setattr(m,'_chat',lambda *args:completion('invalid JSON'))
    with pytest.raises(RSIError):m.complete([{'role':'user','content':'x'}],rid)
    assert r.usage(rid)['actual']==25
    response=completion();response['output']=[{'type':'function_call','name':'exec','arguments':'touch unwanted'}]
    monkeypatch.setattr(m,'_chat',lambda *args:response)
    with pytest.raises(RSIError):m.complete([{'role':'user','content':'x'}],rid)
    assert not (tmp_path/'unwanted').exists()

def test_token_overrun_stops_and_stays_accounted(model,monkeypatch):
    m,r,rid=model;response=completion();response['usage']['input_tokens']=DEFAULTS['max_tokens']+1
    monkeypatch.setattr(m,'_chat',lambda *args:response)
    with pytest.raises(BudgetExceeded):m.complete([{'role':'user','content':'x'}],rid)
    assert r.usage(rid)['actual']>DEFAULTS['max_tokens']
    with pytest.raises(BudgetExceeded):m.complete([{'role':'user','content':'x'}],rid)
    assert r.usage(rid)['n']==1

def slow_transport(token,body,timeout,connection):time.sleep(10)

def test_transport_deadline_kills_child(model,monkeypatch):
    m,r,rid=model;m.cfg['model_timeout']=.2;m.probe()
    monkeypatch.setattr(provider,'_response_exchange',slow_transport)
    before={p.pid for p in multiprocessing.active_children()};start=time.monotonic()
    with pytest.raises(Unavailable):m.complete([{'role':'user','content':'x'}],rid)
    assert time.monotonic()-start<3
    assert {p.pid for p in multiprocessing.active_children()}==before
    assert r.usage(rid)['unknown']==1

def test_no_auth_does_not_fall_back_to_api_key(accounts,monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY','forbidden')
    atomic_json(tmp_path/'state'/'config.json',dict(DEFAULTS,provider='chatgpt',openai_model='model'))
    engine=Engine(tmp_path/'state')
    result=engine.provider_check()
    assert result['status']=='blocked' and result['model_inference_verified'] is False
    assert result['usage']['n']==0

def test_web_account_endpoints_no_secret_or_cross_origin(accounts,monkeypatch,tmp_path):
    import server
    monkeypatch.setenv('NEUROPILOT_RSI_STATE',str(tmp_path/'state'))
    client=server.app.test_client()
    response=client.post('/rsi/api/openai/login',json={})
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert urlsplit(response.json['url']).netloc=='auth.openai.com'
    status=client.get('/rsi/api/openai/status').json
    assert status['login']['status']=='waiting'
    assert 'nonce' not in json.dumps(status) and 'verifier' not in json.dumps(status)
    assert client.post('/rsi/api/openai/configure',json={'model':'invented'}).status_code==400
    assert client.post('/rsi/api/openai/logout',json={},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/rsi/api/openai/cancel',json={}).status_code==200
    assert client.get('/rsi/api/openai/status').json['login']['status']=='cancelled'
    assert load_config(tmp_path/'state')['provider']=='ollama'
