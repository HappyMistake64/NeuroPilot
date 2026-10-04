"""RSI-0..6 orchestration with independent measurement and explicit evidence gates."""
import json
import random
import time
from pathlib import Path
from .benchmark import Benchmark
from .common import RSIError, Unavailable, BudgetExceeded, Cancelled, canonical, digest, load_config, atomic_json, DEFAULTS
from .registry import Registry
from .provider import make_provider
from .sandbox import Sandbox
from .runtime import Runtime
from .evaluation import efficiency_comparison


def implementation_digest():
    root=Path(__file__).parent
    return digest(canonical({str(p.relative_to(root)):digest(p.read_bytes()) for p in sorted(root.rglob('*.py'))}))

def comparison(parent_rows,candidate_rows,min_wins=2):
    def group(rows):
        out={}
        for row in rows: out.setdefault(row['task'],[]).append(row['resolved'])
        return out
    a,b=group(parent_rows),group(candidate_rows)
    if not a or a.keys()!=b.keys() or any(len(a[k])!=len(b[k]) for k in a):
        raise RSIError('Incomplete or unpaired comparison')
    wins=[];losses=[];unstable=[]
    for key in a:
        if len(set(a[key]))>1 or len(set(b[key]))>1: unstable.append(key)
        if not any(a[key]) and all(b[key]): wins.append(key)
        # Conservative: any previously observed success lost in a candidate trial blocks release.
        if any(a[key]) and not all(b[key]): losses.append(key)
    return {'new_wins':wins,'regressions':losses,'unstable':unstable,'parent_resolved':sum(r['resolved'] for r in parent_rows),'candidate_resolved':sum(r['resolved'] for r in candidate_rows),'attempts_each':len(parent_rows),'tasks':len(a),'gate_passed':len(wins)>=min_wins and not losses and not unstable,'interpretation':'pilot operational gate, not a statistical proof'}

class Engine:
    def __init__(self,root,provider=None,sandbox=None):
        self.root=Path(root).resolve();self.registry=Registry(root);self.cfg=load_config(root)
        self.benchmark=Benchmark(root);self.provider=provider or make_provider(self.cfg,self.registry)
        self.sandbox=sandbox or Sandbox(self.cfg)
        self.runtime=Runtime(self.cfg,self.registry,self.provider,self.sandbox)
        self.fingerprint=None
    def init(self):
        if not (self.root/'config.json').exists(): atomic_json(self.root/'config.json',DEFAULTS)
        self.benchmark.init()
        with self.registry.connect() as c: initialized=c.execute("SELECT value FROM meta WHERE key='active'").fetchone()
        if initialized: self.registry.active()
        else:
            self.registry.add_artifact(Path(__file__).with_name('strategies').joinpath('baseline.py').read_text(encoding='utf-8'))
        return self.status()
    def doctor(self):
        result={}
        for name,fn in (('model',self.provider.probe),('sandbox',self.sandbox.probe)):
            try: result[name]={'ok':True,'details':fn()}
            except (RSIError,OSError) as error: result[name]={'ok':False,'error':str(error)}
        result['ready']=all(v['ok'] for v in result.values())
        result['model_inference_verified']=False
        return result
    def status(self):
        result=self.registry.summary()
        try: result['benchmark']=self.benchmark.info()
        except RSIError: result['benchmark']=None
        result['implementation']='RSI 0.3.0; experimental controller'
        result['provider']={'kind':self.cfg['provider'],'model':self.cfg['codex_model'] if self.cfg['provider']=='codex' else self.cfg['openai_model'] if self.cfg['provider']=='chatgpt' else self.cfg['model']}
        result['campaign_estimate']=self.campaign_estimate() if result['benchmark'] else None
        return result
    def _prepare(self,rid):
        self.registry.check(rid)
        model=self.provider.probe(); sandbox=self.sandbox.probe()
        self.fingerprint={'implementation':implementation_digest(),'benchmark':self.benchmark.info(),'model':model,'sandbox':sandbox,'config':dict(self.cfg)}
        if getattr(self,'required_environment',None):
            for key in ('implementation','model','sandbox'):
                if self.fingerprint[key]!=self.required_environment[key]: raise RSIError('Study environment changed: '+key)
        self.registry.event(rid,'environment',self.fingerprint)
        return self.fingerprint
    def _check(self,rid):
        self.registry.check(rid)
        if self.fingerprint:
            if implementation_digest()!=self.fingerprint['implementation'] or self.benchmark.info()!=self.fingerprint['benchmark']:
                raise RSIError('Code or benchmark changed during experiment')
    def _measure(self,artifacts,tasks,repeats,rid):
        results={a['id']:[] for a in artifacts}
        for repeat in range(repeats):
            shuffled=list(tasks);random.Random(repeat).shuffle(shuffled)
            for index,task in enumerate(shuffled):
                order=artifacts if (index+repeat)%2==0 else list(reversed(artifacts))
                for artifact in order:
                    self._check(rid)
                    result=self.runtime.solve(artifact,task,rid,seed=repeat*1000+index*10)
                    results[artifact['id']].append(result)
        return results
    def _run(self,kind,fn):
        with self.registry.exclusive():
            self.registry.active()
            rid=self.registry.new_run(kind,self.cfg)
            report={'run_id':rid,'kind':kind,'generations':[],'actual_rsi_improvement_proven':False}
            try:
                report['environment']=self._prepare(rid)
                fn(rid,report)
                status='complete'
            except Cancelled as error: status='stopped';report['error']=str(error)
            except BudgetExceeded as error: status='budget_exhausted';report['error']=str(error)
            except Unavailable as error: status='blocked';report['error']=str(error)
            except RSIError as error: status='failed';report['error']=str(error)
            except Exception as error:
                status='failed';report['error']=f'{type(error).__name__}: {error}'
            report['status']=status
            report.setdefault('usage',self.registry.usage(rid))
            report['active']=self.registry.active()['id']
            self.registry.finish(rid,status,report)
            return report
    def baseline(self,limit=None):
        if limit is not None and (type(limit) is not int or limit<1): raise RSIError('Limit must be positive')
        def work(rid,report):
            active=self.registry.active();tasks=self.benchmark.tasks('dev')
            if limit: tasks=tasks[:limit]
            if not tasks: raise RSIError('No development tasks')
            self.registry.assert_fresh(tasks)
            results=self._measure([active],tasks,1,rid)[active['id']]
            report.update(artifact=active['id'],results=results,resolved=sum(r['resolved'] for r in results),total=len(results))
        return self._run('baseline',work)

    def provider_check(self):
        """One real inference, independent of code execution and capability evaluation."""
        with self.registry.exclusive():
            rid=self.registry.new_run('provider_check',self.cfg)
            report={'run_id':rid,'kind':'provider_check','model_inference_verified':False,
                    'actual_rsi_improvement_proven':False}
            try:
                report['model']=self.provider.probe()
                result=self.provider.complete([{'role':'user','content':'Return only this JSON object: {"connection":"ok"}'}],rid)
                if result!={'connection':'ok'}: raise RSIError('Connection test returned unexpected JSON')
                report['model_inference_verified']=True;status='complete'
            except Cancelled as error: status='stopped';report['error']=str(error)
            except BudgetExceeded as error: status='budget_exhausted';report['error']=str(error)
            except (Unavailable,OSError) as error: status='blocked';report['error']=str(error)
            except RSIError as error: status='failed';report['error']=str(error)
            report.update(status=status,usage=self.registry.usage(rid))
            self.registry.finish(rid,status,report)
            return report
    def campaign_estimate(self):
        counts=self.benchmark.info()['counts'];steps=self.cfg['steps_per_task'];repeats=self.cfg['repeats']
        calls=3*counts['dev']*steps+1+2*(counts['validation']+counts['final'])*repeats*steps+2*steps
        return {'max_calls_one_generation':calls,'max_reserved_tokens':calls*(self.cfg['context_tokens']+self.cfg['output_tokens']),'note':('Logical request estimate; Codex retries can add requests, all bounded by max_calls. Token numbers are reservations, not a server cap.' if self.cfg['provider'] in ('chatgpt','codex') else 'Upper bound; early rejection reduces work. A smaller budget may end before confirmation.')}
    def _comparison(self,parent,candidate,min_wins):
        result=comparison(parent,candidate,min_wins)
        result['capability_gate_passed']=result['gate_passed']
        result['efficiency']=efficiency_comparison(parent,candidate,self.cfg['min_token_saving_percent'])
        result['efficiency_gate_passed']=self.cfg['allow_efficiency'] and result['efficiency']['gate_passed']
        result['gate_passed']=result['capability_gate_passed'] or result['efficiency_gate_passed']
        return result
    def campaign(self,generations=None,author_id=None):
        n=self.cfg['max_generations'] if generations is None else generations
        if type(n) is not int or not 1<=n<=self.cfg['max_generations']: raise RSIError('Generation count exceeds configured limit')
        def work(rid,report):
            stale=0
            report['estimate']=self.campaign_estimate()
            for index in range(n):
                self._check(rid)
                # Final data may be used at most once; do not spend another generation on an already consumed set.
                with self.registry.connect() as c: used=c.execute('SELECT 1 FROM holdouts WHERE digest=?',(self.benchmark.final_digest(),)).fetchone()
                if used:
                    report['stop_reason']='fresh_final_dataset_required';break
                parent=self.registry.active()
                dev=self.benchmark.tasks('dev');validation=self.benchmark.tasks('validation');final=self.benchmark.tasks('final')
                self.registry.assert_fresh(dev+validation+final)
                if not dev or len(validation)<self.cfg['min_new_wins'] or len(final)<self.cfg['min_new_wins']: raise RSIError('Dataset splits too small')
                author=self.registry.artifact(author_id) if author_id else parent
                gen={'index':index+1,'parent':parent['id'],'author':author['id'],'status':'measuring_parent'};report['generations'].append(gen)
                first=self._measure([parent],dev,1,rid)[parent['id']]
                evidence=[{'task':r['task'],'resolved':r['resolved'],'errors':r['errors'],'patch':r['patch'][:2000],'evaluation':r['evaluation'],'usage':r['usage'],'steps':r['steps'],'elapsed':r['elapsed']} for r in first]
                try: candidate=self.runtime.propose(parent,evidence,rid,author=author)
                except (BudgetExceeded,Cancelled,Unavailable): raise
                except RSIError as error:
                    gen.update(status='proposal_rejected',error=str(error));stale+=1
                    if stale>=self.cfg['stagnation_limit']:report['stop_reason']='stagnation';break
                    continue
                gen['candidate']=candidate['id']
                # Rerun the parent in paired order; proposal evidence is not reused as confirmation.
                development=self._measure([parent,candidate],dev,1,rid)
                gen['development']=self._comparison(development[parent['id']],development[candidate['id']],1)
                if not gen['development']['gate_passed']:
                    gen['status']='rejected_development';self.registry.set_status(candidate['id'],'rejected');stale+=1
                else:
                    measured=self._measure([parent,candidate],validation,self.cfg['repeats'],rid)
                    gen['validation']=self._comparison(measured[parent['id']],measured[candidate['id']],self.cfg['min_new_wins'])
                    if not gen['validation']['gate_passed']:
                        gen['status']='rejected_validation';self.registry.set_status(candidate['id'],'rejected');stale+=1
                    else:
                        self.registry.consume_holdout(self.benchmark.final_digest(),rid,final)
                        measured=self._measure([parent,candidate],final,self.cfg['repeats'],rid)
                        gen['final']=self._comparison(measured[parent['id']],measured[candidate['id']],self.cfg['min_new_wins'])
                        gain_kind=next((kind for kind in ('capability','efficiency') if all(gen[stage][kind+'_gate_passed'] for stage in ('validation','final'))),None)
                        if not gain_kind:
                            gen['status']='rejected_final';self.registry.set_status(candidate['id'],'rejected');stale+=1
                        else:
                            self.registry.set_status(candidate['id'],'accepted');gen['status']='accepted';stale=0
                            # Accepted is not the same as externally established general RSI progress.
                            gen['gain_kind']=gain_kind
                            report['pilot_'+gain_kind+'_gain_confirmed']=True
                            gen['canary_task']=next((r['task'] for r in development[candidate['id']] if r['resolved']),None)
                            self._checkpoint(rid,report)
                            if self.cfg['auto_promote']:
                                self._activate(candidate,parent,rid,dev,development[candidate['id']]);gen['status']='promoted'
                            else:
                                report['stop_reason']='accepted_candidate_ready_for_activation';break
                self.registry.event(rid,'generation_finished',gen)
                self._checkpoint(rid,report)
                if stale>=self.cfg['stagnation_limit']: report['stop_reason']='stagnation';break
            else: report['stop_reason']='generation_limit'
        return self._run('campaign',work)
    def _checkpoint(self,rid,report):
        with self.registry.connect() as c:c.execute('UPDATE runs SET report=? WHERE id=?',(canonical(report),rid))
    def _activate(self,candidate,parent,rid,tasks,rows=None):
        # Test the policy before activation, then run a previously solved public development task.
        self._check(rid)
        if rows:
            solved={r['task'] for r in rows if r['resolved']};task=next((t for t in tasks if t['id'] in solved),None)
        else: task=tasks[0] if tasks else None
        if task is None: raise RSIError('No canary task available')
        before=self.runtime.solve(candidate,task,rid)
        if not before['resolved']:
            self.registry.set_status(candidate['id'],'canary_failed')
            raise RSIError('Candidate canary failed before activation')
        self.registry.promote(candidate['id'],parent['id'],'validated pilot and canary')
        try:
            after=self.runtime.solve(candidate,task,rid)
            if not after['resolved']: raise RSIError('Canary failed after activation')
        except BaseException:
            self.registry.rollback();self.registry.set_status(candidate['id'],'canary_failed');raise
        self.registry.event(rid,'promoted',{'artifact':candidate['id'],'previous':parent['id']})
    def activate(self,aid):
        candidate=self.registry.artifact(aid)
        if candidate['status']!='accepted': raise RSIError('Candidate has not passed the gates')
        receipt=None
        with self.registry.connect() as c:
            for row in c.execute("SELECT report FROM runs WHERE kind='campaign' AND status='complete' ORDER BY created DESC"):
                data=json.loads(row[0])
                if any(g.get('candidate')==aid and g['status'] in ('accepted','promoted') for g in data.get('generations',[])):
                    receipt=data;break
        if receipt is None: raise RSIError('No completed evaluation receipt for this candidate')
        def work(rid,report):
            old=receipt['environment'];now=report['environment']
            if any(old[k]!=now[k] for k in ('implementation','benchmark','model','sandbox')): raise RSIError('Evaluation environment changed; evaluate again')
            for key in ('steps_per_task','context_tokens','output_tokens','sandbox_timeout','memory_mb','repeats','min_new_wins','allow_efficiency','min_token_saving_percent'):
                if old['config'][key]!=now['config'][key]: raise RSIError('Evaluation configuration changed; evaluate again')
            parent=self.registry.active()
            accepted_gen=next(g for g in receipt['generations'] if g.get('candidate')==aid and g['status'] in ('accepted','promoted'))
            tasks=[t for t in self.benchmark.tasks('dev') if t['id']==accepted_gen.get('canary_task')]
            self._activate(candidate,parent,rid,tasks)
            report.update(artifact=aid,previous=parent['id'])
        return self._run('activate',work)
    def reference_check(self):
        # Does not contact a model. Candidate execution still requires the verified sandbox.
        with self.registry.exclusive():
            rid=self.registry.new_run('reference_check',self.cfg);results=[]
            try:
                self.sandbox.probe()
                for task in self.benchmark.load():
                    reference=task.get('reference')
                    if not isinstance(reference,str): raise RSIError('Reference unavailable')
                    good=self.runtime.evaluate_code({'solution.py':reference},task['public']+task['hidden'],rid)
                    bad=self.runtime.evaluate_code(task['files'],task['public']+task['hidden'],rid)
                    results.append({'task':task['id'],'reference_passed':good['passed'],'bug_detected':not bad['passed']})
                status='complete' if all(r['reference_passed'] and r['bug_detected'] for r in results) else 'failed'
                report={'results':results,'status':status,'run_id':rid,'model_used':False}
            except (RSIError,OSError) as error: status='blocked';report={'status':status,'run_id':rid,'error':str(error),'results':results,'model_used':False}
            self.registry.finish(rid,status,report);return report
