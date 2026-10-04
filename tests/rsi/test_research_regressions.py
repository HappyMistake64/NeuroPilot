"""Regression cases discovered by the October controller research."""
import copy,json
import pytest
from rsi.common import RSIError,atomic_json,DEFAULTS
from rsi.runtime import equivalent,Runtime
from rsi.registry import Registry
from rsi.engine import Engine
from rsi.benchmark import validate
from rsi.catalog import catalog
from rsi.sandbox import Result
from test_integration import FixtureProvider,FixtureSandbox

@pytest.mark.parametrize('a,b,expected',[(10**12,10**12+1,False),(10**400,10**400,True),
 (10**400,10**400+1,False),(10**12,float(10**12)+.25,False),(4,4.0,True),
 (4.0,4,True),(1.1,1.1+1e-12,True),(True,1,False),(1,True,False)])
def test_exact_integers(a,b,expected):assert equivalent(a,b) is expected

@pytest.mark.parametrize('tokens',[-1,0,True,1.5])
def test_invalid_reservations_do_not_reduce_usage(tmp_path,tokens):
 r=Registry(tmp_path);rid=r.new_run('test',DEFAULTS)
 with pytest.raises(RSIError):r.reserve(rid,tokens)
 assert r.usage(rid)['n']==0 and r.usage(rid)['charged']==0

@pytest.mark.parametrize('output,passed',[('[{"ok":true}]',False),('[{"ok":true,"value":null}]',True)])
def test_null_requires_explicit_value(tmp_path,output,passed):
 r=Registry(tmp_path);rid=r.new_run('test',DEFAULTS)
 class Output:
  def run(self,*args,**kwargs):return Result(0,output,'',.001)
 runner=Runtime(DEFAULTS,r,None,Output())
 assert runner.evaluate_code({'solution.py':'unused'},[{'args':[],'expected':None}],rid)['passed'] is passed


def test_cross_split_clone_with_renamed_family_rejected():
 tasks=catalog();duplicate=copy.deepcopy(tasks[0]);duplicate.update(id='copy',family='renamed',split='final')
 with pytest.raises(RSIError,match='Duplicate'):validate(tasks+[duplicate])


def test_bad_files_schema_is_controlled_error():
 t=copy.deepcopy(catalog()[0]);t['files']=None
 with pytest.raises(RSIError):validate([t])

@pytest.mark.parametrize('mode',['baseline','campaign'])
def test_retired_holdout_never_reaches_provider(tmp_path,mode):
 r=Registry(tmp_path);p=FixtureProvider(r,improve=False);e=Engine(tmp_path,p,FixtureSandbox());e.init()
 retired=copy.deepcopy(catalog()[40]);r.consume_holdout('old','old',[retired]);retired.update(id='dev-retired',split='dev')
 tasks=[retired]+[t for t in catalog() if (t['split']=='validation' and int(t['id'].split('-')[-1])<=2) or (t['split']=='final' and 2<=int(t['id'].split('-')[-1])<=3)]
 atomic_json(e.benchmark.path,tasks)
 result=e.baseline() if mode=='baseline' else e.campaign(1)
 assert result['status']=='failed' and 'consumed holdout' in result['error']
 assert not p.requests


def test_malformed_tool_argument_is_recoverable(tmp_path):
 r=Registry(tmp_path)
 class WrongArgument(FixtureProvider):
  def complete(self,*args,**kwargs):
   super().complete(*args,**kwargs)
   return {'actions':[{'tool':'read_file','path':[]},{'tool':'finish'}]}
 e=Engine(tmp_path,WrongArgument(r),FixtureSandbox());e.init()
 result=e.baseline(limit=1)
 assert result['status']=='complete' and result['resolved']==0
 with r.connect() as c:events=[json.loads(row[0]) for row in c.execute("SELECT payload FROM events WHERE kind='tool'")]
 assert 'error' in events[0]['result']
