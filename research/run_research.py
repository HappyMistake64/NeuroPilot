"""Reproducible controller research. No model/candidate code is executed on host.
Only the fixed, authored catalog reference/broken functions are evaluated here.
Use --project for the archived 3.3.0 tree to reproduce the before measurements.
"""
import argparse,copy,json,math,os,statistics,sys,tempfile,time,tracemalloc
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
parser=argparse.ArgumentParser()
parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--suite',choices=['benchmark','gates','robustness','stress'],required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
sys.path[:0]=[str(args.project.resolve()),str(args.project.resolve()/'tests'/'rsi')]
from rsi.common import DEFAULTS,RSIError,BudgetExceeded,Unavailable,canonical,atomic_json
from rsi.catalog import catalog
from rsi.runtime import equivalent,Runtime
from rsi.registry import Registry
from rsi.engine import Engine,comparison,implementation_digest
from rsi.benchmark import validate
from rsi.sandbox import Result
from test_integration import FixtureProvider,FixtureSandbox


def benchmark():
 rows=[]
 for t in catalog():
  good={};bad={}
  # Authored functions only, with fixed bounded authored arguments.
  exec(t['reference'],good);exec(t['files']['solution.py'],bad)
  def check(fn,c):
   try:return equivalent(fn(*copy.deepcopy(c['args'])),c['expected'])
   except Exception:return False
  checks=t['public']+t['hidden']
  rows.append({'id':t['id'],'family':t['family'],'split':t['split'],
   'reference_passed':all(check(good['solve'],c) for c in checks),
   'broken_passes_public':all(check(bad['solve'],c) for c in t['public']),
   'broken_passes_all':all(check(bad['solve'],c) for c in checks),
   'public_checks':len(t['public']),'hidden_checks':len(t['hidden'])})
 # Deliberately white-box memorization: a table of ALL known answers. This is
 # an evaluator stress control, NOT an agent-generated solution or data leak.
 lookup_passes=0
 for t in catalog():
  table={canonical(c['args']):c['expected'] for c in t['public']+t['hidden']}
  lookup_passes+=all(equivalent(table[canonical(c['args'])],c['expected']) for c in t['public']+t['hidden'])
 # Independent arithmetic oracles on extra bounded inputs for six task families.
 extra=[]
 for t in catalog():
  cases=[];f=t['family']
  if f=='absolute':cases=[([x],x if x>=0 else -x) for x in range(-100,101)]
  if f=='inclusive_sum':cases=[([n],n*(n+1)//2) for n in range(201)]
  if f=='factorial':
   value=1
   for n in range(21):
    if n:value*=n
    cases.append(([n],value))
  if f=='gcd':cases=[([a,b],max(d for d in range(1,max(a,b)+1) if a%d==b%d==0)) for a in range(1,31) for b in range(1,31)]
  if f=='ceil_div':cases=[([a,b],math.ceil(a/b)) for a in range(-100,101) for b in range(1,11)]
  if f=='clamp':cases=[([x,-10,10],-10 if x<-10 else (10 if x>10 else x)) for x in range(-100,101)]
  if cases:
   ns={};exec(t['reference'],ns)
   extra.append({'family':f,'cases':len(cases),'passed':sum(ns['solve'](*a)==v for a,v in cases)})
 return {'evidence_type':'authored fixture execution; not agent capability', 'tasks':len(rows),
  'reference_tasks_passed':sum(r['reference_passed'] for r in rows),
  'broken_tasks_detected':sum(not r['broken_passes_all'] for r in rows),
  'broken_tasks_not_detected_by_public_check':sum(r['broken_passes_public'] for r in rows),
  'whitebox_lookup_tasks_passed':lookup_passes,'extra_reference_cases':extra,'rows':rows,
  'limitations':'Finite authored cases; whitebox lookup is a control that already knows answers; extra cases cover only six arithmetic families.'}


def gates():
 import numpy as np
 rng=np.random.default_rng(20261004);n=50000;out=[];crosschecks=0
 scenarios=[('null_half',[.5]*20,[.5]*20),('gain_half_to_seven_tenths',[.5]*20,[.7]*20),
  ('nearly_deterministic_four_new_wins',[.02]*10+[.98]*10,[.98]*4+[.02]*6+[.98]*10),
  ('deterministic_four_new_wins',[0]*10+[1]*10,[1]*4+[0]*6+[1]*10)]
 def gate(a,b):
  win=(~a.any(2)&b.all(2)).sum(1)
  regression=(a.any(2)&~b.all(2)).any(1)
  unstable=((a.any(2)!=a.all(2))|(b.any(2)!=b.all(2))).any(1)
  return (win>=2)&~regression&~unstable
 for label,pa,pb in scenarios:
  for repeats in (1,3,5):
   totals=[0,0]
   for start in range(0,n,5000):
    a=rng.random((5000,20,repeats))<np.array(pa)[None,:,None]
    b=rng.random((5000,20,repeats))<np.array(pb)[None,:,None]
    passed=gate(a,b)
    # Independent second confirmation split, same modeled probabilities.
    c=rng.random((5000,20,repeats))<np.array(pa)[None,:,None]
    d=rng.random((5000,20,repeats))<np.array(pb)[None,:,None]
    totals[0]+=int(passed.sum());totals[1]+=int((passed&gate(c,d)).sum())
    if start==0:
     for index in range(20):
      rows=lambda x:[{'task':str(t),'resolved':bool(v)} for t,vs in enumerate(x) for v in vs]
      assert comparison(rows(a[index]),rows(b[index]))['gate_passed']==bool(passed[index]);crosschecks+=1
   out.append({'scenario':label,'tasks_per_split':20,'repeats':repeats,'simulations':n,
    'one_split_accepted':totals[0],'both_splits_accepted':totals[1],
    'one_split_percent':totals[0]/n*100,'both_splits_percent':totals[1]/n*100})
 efficiency=[]
 from rsi.evaluation import efficiency_comparison
 for mode,true_saving in [('independent_noise',0),('independent_noise',.1),('independent_noise',.2),('shared_run_drift',0)]:
  passed_total=0
  for start in range(0,n,5000):
   shape=(5000,60) if mode=='independent_noise' else (5000,1)
   a=np.rint(1000*rng.lognormal(-.3**2/2,.3,shape)).astype(int)
   b=np.rint(1000*(1-true_saving)*rng.lognormal(-.3**2/2,.3,shape)).astype(int)
   if mode=='shared_run_drift':a=np.repeat(a,60,axis=1);b=np.repeat(b,60,axis=1)
   passed=b.sum(1)<=.85*a.sum(1)+1e-9;passed_total+=int(passed.sum())
   if start==0:
    for i in range(20):
     rows=lambda x:[{'task':str(j//3),'seed':j%3,'resolved':True,'usage':{'actual_tokens':int(v)}} for j,v in enumerate(x)]
     assert efficiency_comparison(rows(a[i]),rows(b[i]))['gate_passed']==bool(passed[i]);crosschecks+=1
  efficiency.append({'noise':mode,'true_token_saving_percent':true_saving*100,'simulations':n,'accepted':passed_total,'accepted_percent':passed_total/n*100})
 return {'evidence_type':'Monte Carlo simulation, not model measurements','seed':20261004,
  'capability':out,'efficiency':efficiency,'actual_gate_crosschecks':crosschecks,
  'assumptions':'Independent Bernoulli trials and independent confirmation splits for capability; lognormal token noise sigma=0.3 with stable successful outcomes for efficiency. Shared drift uses one factor across an entire measurement. No actual provider was called.'}


def robustness():
 results=[]
 def probe(name,fn):
  try:value=fn();results.append({'name':name,'result':value})
  except Exception as error:results.append({'name':name,'exception':type(error).__name__,'message':str(error)[:200]})
 probe('wrong_large_integer_accepted',lambda:equivalent(10**12,10**12+1))
 probe('huge_equal_integer_comparison',lambda:equivalent(10**400,10**400))
 probe('bool_confused_with_integer',lambda:equivalent(True,1))
 with tempfile.TemporaryDirectory() as temp:
  r=Registry(temp);e=Engine(temp,FixtureProvider(r),FixtureSandbox());e.init();rid=e.registry.new_run('research',DEFAULTS)
  class MissingValue:
   def run(self,*a,**kw):return Result(0,'[{"ok":true}]','',.001)
  runtime=Runtime(e.cfg,e.registry,e.provider,MissingValue())
  probe('missing_value_accepted_as_null',lambda:runtime.evaluate_code({'solution.py':'unused'},[{'args':[],'expected':None}],rid)['passed'])
  task=catalog()[0];root=Path(temp)/'task';root.mkdir();(root/'solution.py').write_text(task['files']['solution.py'])
  probe('malformed_tool_path',lambda:e.runtime.tool(root,task,{'tool':'read_file','path':[]},rid))
  probe('negative_reservation',lambda:e.registry.reserve(rid,-100))
  probe('charged_after_negative_reservation',lambda:e.registry.usage(rid)['charged'])
 data=catalog();duplicate=copy.deepcopy(data[0]);duplicate.update(id='different',family='different',split='final');data.append(duplicate)
 probe('cross_split_clone_accepted',lambda:bool(validate(data)))
 with tempfile.TemporaryDirectory() as temp:
  r=Registry(temp);provider=FixtureProvider(r,improve=False);e=Engine(temp,provider,FixtureSandbox());e.init()
  retired=copy.deepcopy(catalog()[40]);r.consume_holdout('retired','old',[retired]);retired.update(id='dev-retired',split='dev')
  atomic_json(e.benchmark.path,[retired]+[t for t in catalog() if (t['split']=='validation' and int(t['id'].split('-')[-1])<=2) or (t['split']=='final' and 2<=int(t['id'].split('-')[-1])<=3)])
  result=e.campaign(1)
  leaked=any('dev-retired' in json.dumps(m) for m in provider.requests)
  results.append({'name':'retired_holdout_reaches_development_provider','result':leaked,'run_status':result['status'],'error':result.get('error')})
 return {'evidence_type':'direct boundary probes; fake output and explicit provider fixtures only','probes':results}


def stress():
 quota=[]
 for trial in range(10):
  with tempfile.TemporaryDirectory() as temp:
   r=Registry(temp);rid=r.new_run('quota',dict(DEFAULTS,max_calls=50,max_tokens=5000))
   def reserve(_):
    try:r.reserve(rid,100);return True
    except BudgetExceeded:return False
   with ThreadPoolExecutor(max_workers=32) as pool:accepted=sum(pool.map(reserve,range(500)))
   quota.append({'attempts':500,'accepted':accepted,'usage':r.usage(rid),'audit_valid':r.check_chain()})
 timings=[];fd=lambda:len(list(Path('/proc/self/fd').iterdir()))
 with tempfile.TemporaryDirectory() as temp:
  r=Registry(temp);e=Engine(temp,FixtureProvider(r),FixtureSandbox());e.init()
  tracemalloc.start();before=tracemalloc.get_traced_memory()[0];fds=fd()
  for i in range(500):
   begin=time.perf_counter();Engine(temp).status();timings.append(time.perf_counter()-begin)
  allocated,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
  repeated={'iterations':500,'fd_before':fds,'fd_after':fd(),'python_live_bytes_delta':allocated-before,'python_peak_bytes':peak,
   'median_ms':statistics.median(timings)*1000,'p95_ms':sorted(timings)[474]*1000}
 scale=[]
 with tempfile.TemporaryDirectory() as temp:
  r=Registry(temp);r.add_artifact('trusted research marker');count=0
  for target in (0,1000,10000):
   for index in range(count,target):r.event(None,'research',{'index':index,'text':'x'*1024})
   count=target;values=[]
   for _ in range(20):
    begin=time.perf_counter();r.summary();values.append(time.perf_counter()-begin)
   scale.append({'events':target,'median_status_ms':statistics.median(values)*1000,'p95_status_ms':sorted(values)[18]*1000})
 failures=[]
 for nth in (1,3,5,10,20,30):
  for repetition in range(3):
   with tempfile.TemporaryDirectory() as temp:
    r=Registry(temp)
    class Outage(FixtureProvider):
     count=0
     def complete(self,*a,**kw):
      self.count+=1
      if self.count==nth:raise Unavailable('injected research outage')
      return super().complete(*a,**kw)
    p=Outage(r);e=Engine(temp,p,FixtureSandbox());e.init();old=e.registry.active()['id']
    atomic_json(e.benchmark.path,[t for t in catalog() if int(t['id'].split('-')[-1])<=2])
    result=e.campaign(1)
    failures.append({'nth_call':nth,'repetition':repetition,'status':result['status'],
     'active_unchanged':e.registry.active()['id']==old,'audit_valid':r.check_chain()})
 return {'evidence_type':'actual SQLite/OS measurements; outage scenarios use explicit fixtures','quota_trials':quota,
  'repeated_status':repeated,'audit_scaling':scale,'injected_outages':failures,
  'limitations':'One shared host, not the user 8GB laptop; Python allocation tracing is not total model or system RAM.'}

start=time.perf_counter()
result={'suite':args.suite,'implementation_sha256':implementation_digest(),'python':sys.version.split()[0],
 'result':globals()[args.suite](),'elapsed_seconds':time.perf_counter()-start,'real_model_used':False}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'suite':args.suite,'output':str(args.output),'elapsed_seconds':result['elapsed_seconds']}))
