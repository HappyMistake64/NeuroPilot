import concurrent.futures
import importlib
import json
import socket
import sys
import time
import zipfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import ai_tools
import chat_wrapper
from run_chat import create_agent, MODULES
from storage import JsonStore
from web_tools import validate_url, clean_text, CheckedRedirect

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'store', JsonStore(tmp_path/'data.json', {'notes':[], 'tasks':[], 'habits':[]}, server.validate_data))
    monkeypatch.setattr(server, 'agent_chat', lambda text, timeout: 'Odpověď: '+text)
    server.app.config['TESTING'] = True
    return server.app.test_client()

def test_ui(client):
    assert client.get('/').status_code == 200
    js = client.get('/app.js')
    assert js.status_code == 200 and b'async function api' in js.data
    assert client.get('/config.json').status_code == 404

def test_chat_persistence(client):
    note = client.post('/think', json={'text':'Ahoj'}).json['note']
    assert client.get('/notes').json == [note]
    assert client.delete('/notes/'+note['id']).status_code == 200
    assert client.get('/notes').json == []

def test_tasks(client):
    task = client.post('/tasks', json={'text':'Učit se'}).json['task']
    assert client.post('/tasks/'+task['id']+'/toggle', json={}).json['task']['done'] is True
    assert client.post('/tasks/'+task['id']+'/toggle', json={}).json['task']['done'] is False
    assert client.delete('/tasks/'+task['id']).status_code == 200
    assert client.delete('/tasks/'+task['id']).status_code == 404

def test_habits(client):
    habit = client.post('/habits', json={'title':'Číst'}).json['habit']
    route = '/habits/'+habit['id']
    day = server.date.today().isoformat()
    assert client.post(route+'/toggle', json={'date':day}).json['habit']['records'] == [day]
    stats = client.get(route+'/stats/7').json
    assert len(stats) == 7 and stats[-1]['done']
    assert client.post(route+'/toggle', json={'date':day}).json['habit']['records'] == []
    assert client.get(route+'/stats/367').status_code == 400
    assert client.post(route+'/toggle', json={'date':'wrong'}).status_code == 400

@pytest.mark.parametrize('value', [None, [], 'hello', 1, {'text':[]}, {'text':''}, {'text':' '*2}, {'text':'x'*20001}])
def test_invalid_inputs(client, value):
    assert client.post('/think', data=json.dumps(value), content_type='application/json').status_code == 400

def test_malformed_json(client):
    assert client.post('/tasks', data='{', content_type='application/json').status_code == 400
    assert client.post('/tasks', data='hello').status_code == 415

def test_import_export(client):
    data = {'notes':[], 'tasks':[{'id':123, 'text':'Starý úkol'}]}
    assert client.post('/import', json=data).status_code == 200
    export = client.get('/export')
    assert export.status_code == 200 and 'attachment' in export.headers['Content-Disposition']
    assert export.json['habits'] == []
    assert client.post('/tasks/123/toggle', json={}).json['task']['done']
    before = client.get('/export').data
    assert client.post('/import', json={'notes':[], 'tasks':[{'id':123,'text':False}]}).status_code == 400
    assert client.get('/export').data == before

@pytest.mark.parametrize('data', [
    {'notes':[], 'tasks':[], 'habits':False},
    {'notes':[], 'tasks':[{'id':1,'text':'a'},{'id':1,'text':'b'}]},
    {'notes':[], 'tasks':[], 'habits':[{'id':1,'title':'a','records':['invalid']}]},
    {'notes':[{'id':1, 'text':'a', 'ai':[]}], 'tasks':[]},
])
def test_import_reject(client, data):
    assert client.post('/import', json=data).status_code == 400

def test_origin(client):
    assert client.post('/tasks', json={'text':'a'}, headers={'Origin':'https://evil.test'}).status_code == 403
    assert client.get('/health', headers={'Host':'evil.test'}).status_code == 403
    assert client.post('/tasks', json={'text':'a'}, headers={'Origin':'http://localhost'}).status_code == 201

def test_concurrent_storage(tmp_path):
    store = JsonStore(tmp_path/'data.json', {'items':[]})
    def append(i): store.update(lambda data: data['items'].append(i))
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(append, range(200)))
    assert sorted(store.read()['items']) == list(range(200))
    assert not list(tmp_path.glob('.json-*'))

def test_corrupt_storage_preserved(tmp_path):
    path = tmp_path/'data.json'; path.write_text('{bad')
    store = JsonStore(path, {})
    with pytest.raises(ValueError): store.update(lambda data: data.update(x=1))
    assert path.read_text() == '{bad'

def test_all_modules_registered():
    agent = create_agent()
    assert len(agent.mods) == len(MODULES) == 15
    assert agent.state['web_cfg']['enabled'] is False
    assert isinstance(agent.chat('Ahoj'), str)

def test_state_and_commands(tmp_path):
    agent = create_agent(); agent.state['basepath'] = str(tmp_path)
    agent.chat('první'); agent.chat('druhý')
    assert len(agent.state['wm_state']) == 2
    assert 'Nastavuji working_memory.slots' in agent.chat(':rewrite working_memory.slots 3')
    assert agent.state['wm_cfg']['slots'] == 3
    agent.chat('zkoumej nové téma')
    assert agent.state['tasks']
    assert 'Identita uložena' in agent.chat(':save_all')
    restored = create_agent(); restored.state['basepath'] = str(tmp_path)
    assert 'Identita načtena' in restored.chat(':load_all')
    assert restored.state['tasks'] == agent.state['tasks']
    assert restored.state['wm_cfg']['slots'] == 3
    assert len(restored.state['wm_state']) <= 3
    assert 'Δ=+0.05' in restored.chat('fb 1')
    assert 'Feedback musí' in restored.chat('fb 100')
    assert 'konečné číslo' in restored.chat(':self truth nan')

def test_sensor_sandbox(tmp_path):
    agent = create_agent(); agent.state['basepath'] = str(tmp_path)
    (tmp_path/'CaseSensitive.txt').write_text('test')
    assert '4 znaků' in agent.chat(':read CaseSensitive.txt')
    assert 'mimo projekt' in agent.chat(':read ../outside')
    assert 'mimo projekt' in agent.chat(':read /etc/passwd')

def test_regex():
    assert clean_text(b'<script>bad()</script><p>One.</p>\n<p>Two.</p>') == 'One. Two.'
    from proto_conscious.relevance_filter import _summ
    assert _summ('One. Two. '+('x'*100), 20) == 'One. Two.'

def test_public_url_validation(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('8.8.8.8',443))])
    assert validate_url('https://arxiv.org/x', ['arxiv.org'])
    for url in ['https://evilarxiv.org/x', 'https://arxiv.org.evil.com', 'file:///etc/passwd', 'https://user:pass@arxiv.org']:
        with pytest.raises(ValueError): validate_url(url, ['arxiv.org'])
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError): validate_url('https://arxiv.org')
    with pytest.raises(ValueError): CheckedRedirect(None).redirect_request(None, None, 302, '', {}, 'http://localhost')

@pytest.mark.parametrize('name', ['../escape', '/tmp/escape', '', 'x'*81, 'a/b'])
def test_project_name_rejected(name):
    with pytest.raises(ValueError): ai_tools.project_zip(name, 'spec')

@pytest.mark.parametrize('filename', ['../escape.txt', '/tmp/escape.txt', 'C:\\escape.txt', 'a/../../escape.txt'])
def test_generated_path_rejected(monkeypatch, filename):
    monkeypatch.setattr(ai_tools, 'llm', lambda *a: f'--FILENAME: {filename}\ncode\n--END')
    with pytest.raises(ValueError): ai_tools.project_zip('project', 'spec')

def test_project_zip(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_tools, 'BASE', tmp_path)
    monkeypatch.setattr(ai_tools, 'llm', lambda *a: '--FILENAME: src/index.html\n<h1>OK</h1>\n--END')
    path = ai_tools.project_zip('Project', 'spec')
    with zipfile.ZipFile(path) as z:
        assert z.namelist() == ['src/index.html']
        assert z.read('src/index.html') == b'<h1>OK</h1>'
    monkeypatch.setattr(ai_tools, 'llm', lambda *a: 'invalid')
    with pytest.raises(RuntimeError): ai_tools.project_zip('Project', 'spec')

def test_model_disabled(monkeypatch):
    monkeypatch.delenv('NEUROPILOT_MODEL', raising=False)
    with pytest.raises(RuntimeError, match='Model není nastaven'): ai_tools.llm('prompt')

def test_model_new_tokens(monkeypatch):
    monkeypatch.setenv('NEUROPILOT_MODEL', 'fake')
    calls = []
    def fake(prompt, **kwargs):
        calls.append(kwargs); return [{'generated_text':'answer'}]
    monkeypatch.setattr(ai_tools, '_pipe', fake)
    assert ai_tools.llm('x'*20000, 200) == 'answer'
    assert calls[0]['max_new_tokens'] == 200 and calls[0]['return_full_text'] is False

@pytest.mark.parametrize('steps', ['0','9','a','1.5',None])
def test_plan_bounds(steps):
    with pytest.raises(ValueError): ai_tools.autonomy_run('goal', steps)

def test_plan_never_fetches_model_url(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_tools, 'MEMORY', JsonStore(tmp_path/'memory.json', {'notes':[], 'history':[]}))
    monkeypatch.setattr(ai_tools, 'llm', lambda *a: '1. https://example.com')
    monkeypatch.setattr(ai_tools, 'fetch_url', lambda *a: pytest.fail('unexpected request'))
    assert 'bez provádění příkazů' in ai_tools.autonomy_run('goal', 1)

def test_worker_timeout_and_recovery(monkeypatch):
    class Agent:
        def chat(self, text):
            if text == 'slow': time.sleep(.05)
            return text
    monkeypatch.setattr(chat_wrapper, '_agent', Agent())
    chat_wrapper._init_agent_safe()
    # Initialization may have supplied the real agent; replace it after startup.
    monkeypatch.setattr(chat_wrapper, '_agent', Agent())
    assert 'Časový limit' in chat_wrapper.chat('slow', timeout=.001)
    assert chat_wrapper.chat('next', timeout=1) == 'next'
    assert chat_wrapper._requests.unfinished_tasks == 0

def test_model_context_reserved(monkeypatch):
    from types import SimpleNamespace
    class Tokenizer:
        model_max_length = 1000
        truncation_side = 'right'
        def encode(self, text, **kwargs):
            assert self.truncation_side == 'left'
            assert kwargs['max_length'] == 800
            return [1,2]
        def decode(self, tokens, **kwargs): return 'short prompt'
    class Pipeline:
        tokenizer = Tokenizer()
        model = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=1000))
        def __call__(self, prompt, **kwargs):
            assert prompt == 'short prompt'
            return [{'generated_text':'answer'}]
    pipe = Pipeline()
    monkeypatch.setenv('NEUROPILOT_MODEL','fake')
    monkeypatch.setattr(ai_tools,'_pipe',pipe)
    assert ai_tools.llm('x'*10000,200) == 'answer'
    assert pipe.tokenizer.truncation_side == 'right'
    with pytest.raises(ValueError): ai_tools.llm('prompt',1000)


@pytest.mark.parametrize('origin', [
    'https://localhost', 'http://localhost:5001', 'null',
    'http://user@localhost', 'http://localhost/path', 'http://localhost?x=1',
    'http://localhost#fragment', 'http://[broken',
])
def test_strict_origin_rejects_before_mutation(client, origin):
    assert client.post('/tasks', json={'text':'blocked'}, headers={'Origin':origin}).status_code == 403
    assert client.get('/tasks').json == []


@pytest.mark.parametrize('site', ['cross-site', 'same-site'])
def test_browser_metadata_blocks_originless_mutations(client, site):
    assert client.post('/tasks', json={'text':'blocked'}, headers={'Sec-Fetch-Site':site}).status_code == 403
    assert client.post('/rsi/api/init', headers={'Sec-Fetch-Site':site}).status_code == 403


def test_equivalent_origin_and_local_clients_still_work(client):
    assert client.post('/tasks', json={'text':'browser'}, headers={'Origin':'http://LOCALHOST:80','Sec-Fetch-Site':'same-origin'}).status_code == 201
    assert client.post('/tasks', json={'text':'local CLI'}).status_code == 201


@pytest.mark.parametrize('host', ['attacker@localhost', 'localhost/path', '[broken', 'localhost:invalid'])
def test_malformed_host_is_rejected(client, host):
    assert client.get('/health', headers={'Host':host}).status_code == 403


@pytest.mark.parametrize('path', ['/', '/rsi', '/tasks', '/export', '/missing'])
def test_browser_protections_cover_pages_data_and_errors(client, path):
    response = client.get(path)
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    policy = response.headers['Content-Security-Policy']
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy and "base-uri 'none'" in policy
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    if response.is_json:
        assert response.headers['Cache-Control'] == 'no-store'


def test_public_error_boundary_never_returns_arbitrary_exception_text():
    from web_errors import public_error
    for error in (OSError('/private/credentials/session.json'), ValueError('fixture-sensitive-value'), RuntimeError({'token':'fixture-sensitive-value'})):
        message = public_error(error)
        assert 'fixture-sensitive-value' not in message and '/private/' not in message
    assert public_error(ValueError('Datum musí mít formát YYYY-MM-DD.')) == 'Datum musí mít formát YYYY-MM-DD.'


def test_rsi_http_errors_do_not_expose_internal_details(client, monkeypatch):
    from rsi import web
    from rsi.common import RSIError
    def failed_engine():
        raise RSIError('fixture-sensitive-value /private/credentials/session.json')
    monkeypatch.setattr(web, 'engine', failed_engine)
    response = client.post('/rsi/api/codex/configure', json={'model':'fixture'})
    assert response.status_code == 400
    assert b'fixture-sensitive-value' not in response.data and b'/private/' not in response.data
    assert response.json['error']


def test_planner_error_handler_does_not_echo_internal_value_error(client, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('fixture-sensitive-value')
    monkeypatch.setattr(server, 'agent_chat', fail)
    response = client.post('/think', json={'text':'hello'})
    assert response.status_code == 400 and b'fixture-sensitive-value' not in response.data
