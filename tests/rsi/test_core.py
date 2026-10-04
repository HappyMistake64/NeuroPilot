import ast
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from rsi.common import *
from rsi.catalog import catalog
from rsi.benchmark import Benchmark,validate
from rsi.registry import Registry
from rsi.runtime import equivalent,validate_strategy,Runtime
from rsi.engine import comparison,Engine

@pytest.mark.parametrize('task',catalog(),ids=lambda t:t['id'])
def test_authored_reference_and_bug(task):
    # ONLY trusted, authored built-in fixtures run here; no model-generated code.
    expected=[x['expected'] for x in task['public']+task['hidden']]
    scope={};exec(task['reference'],scope)
    actual=[scope['solve'](*x['args']) for x in task['public']+task['hidden']]
    assert equivalent(actual,expected)
    broken={};exec(task['files']['solution.py'],broken)
    failed=False
    for case in task['public']+task['hidden']:
        try:failed |= not equivalent(broken['solve'](*case['args']),case['expected'])
        except Exception:failed=True
    assert failed,'Fixture must expose an actual bug'

def test_disjoint_benchmark_and_identity(tmp_path):
    bench=Benchmark(tmp_path);info=bench.init()
    assert info['counts']=={'dev':20,'validation':20,'final':20}
    tasks=bench.load();tasks[20]['family']=tasks[0]['family']
    with pytest.raises(RSIError,match='leakage'):validate(tasks)
    tasks=bench.load();sha=bench.final_digest()
    for task in tasks:task['id']='renamed-'+task['id']
    atomic_json(bench.path,tasks)
    assert bench.final_digest()==sha

@pytest.mark.parametrize('name',['../secret','/etc/passwd','a/../../x','x\\y','.secret','x:y',''])
def test_path_rejections(tmp_path,name):
    with pytest.raises(RSIError):relative_file(tmp_path,name)

def test_symlink(tmp_path):
    (tmp_path/'link').symlink_to('/tmp')
    with pytest.raises(RSIError):relative_file(tmp_path,'link/file')

def test_budget_concurrent(tmp_path):
    r=Registry(tmp_path);cfg=dict(DEFAULTS,max_calls=5,max_tokens=100)
    rid=r.new_run('test',cfg)
    def reserve(_):
        try:return r.reserve(rid,20)
        except BudgetExceeded:return None
    with ThreadPoolExecutor(max_workers=12) as pool:ids=list(pool.map(reserve,range(30)))
    assert sum(i is not None for i in ids)==5
    assert r.usage(rid)['charged']==100
    assert r.usage(rid)['unknown']==5

def test_failed_calls_are_not_free(tmp_path):
    r=Registry(tmp_path);rid=r.new_run('test',dict(DEFAULTS,max_calls=1))
    call=r.reserve(rid,100);r.settle(call,None,{},'failed')
    assert r.usage(rid)['charged']==100
    with pytest.raises(BudgetExceeded):r.reserve(rid,1)

def test_stop_deadline_and_audit(tmp_path):
    r=Registry(tmp_path);rid=r.new_run('test',DEFAULTS);r.stop(rid)
    with pytest.raises(Cancelled):r.check(rid)
    assert r.check_chain()
    with r.connect() as c:c.execute("UPDATE events SET payload='{}' WHERE kind='started'")
    assert not r.check_chain()

def test_artifact_and_release_integrity(tmp_path):
    r=Registry(tmp_path);a=r.add_artifact('a');b=r.add_artifact('b',a)
    with pytest.raises(RSIError):r.promote(b,a,'test')
    r.set_status(b,'accepted');r.promote(b,a,'test')
    assert r.active()['id']==b
    assert r.rollback()==a
    with pytest.raises(RSIError,match='No previous'):r.rollback()
    with r.connect() as c:c.execute("UPDATE artifacts SET source='tamper' WHERE id=?",(a,))
    with pytest.raises(RSIError,match='integrity'):r.active()

def test_holdout_once(tmp_path):
    r=Registry(tmp_path);r.consume_holdout('sha','first')
    with pytest.raises(RSIError):r.consume_holdout('sha','second')

def test_lock(tmp_path):
    r=Registry(tmp_path)
    with r.exclusive():
        with pytest.raises(RSIError):
            with r.exclusive():pass

def rows(values):return [{'task':k,'resolved':x} for k,vs in values.items() for x in vs]

def test_evidence_gate():
    parent=rows({'a':[False]*3,'b':[False]*3,'c':[True]*3})
    candidate=rows({'a':[True]*3,'b':[True]*3,'c':[True]*3})
    assert comparison(parent,candidate)['gate_passed']
    candidate[-1]['resolved']=False
    result=comparison(parent,candidate)
    assert not result['gate_passed'] and result['regressions']==['c']
    assert not comparison(parent,parent)['gate_passed']
    with pytest.raises(RSIError):comparison(parent,[])

def test_no_model_in_init(tmp_path):
    e=Engine(tmp_path);r=e.init()
    assert len(r['artifacts'])==1 and r['runs']==[]
    assert e.campaign_estimate()['max_calls_one_generation']==907
    status=e.doctor()
    assert not status['model']['ok'] and not status['model_inference_verified']

def test_strategy_contract():
    source='def build_context(payload):\n    return "ok"\n'
    assert validate_strategy(source)
    with pytest.raises(RSIError):validate_strategy(source,source)
    with pytest.raises(RSIError):validate_strategy('print("hello")')
    with pytest.raises(RSIError):validate_strategy(source+'\n#extra',source,0)

def test_bool_not_numeric():
    assert not equivalent(True,1)
    assert equivalent(4,4.0)
    assert not equivalent(float('inf'),float('inf'))
