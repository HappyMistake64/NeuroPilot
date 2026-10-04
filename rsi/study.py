"""Precommitted two-arm pilot: fixed author versus recursive author.

All inference uses Engine's real provider. Isolated arms never change the user's
active agent. A single paired study is descriptive, not general RSI proof.
"""
import json
import time
import uuid
from pathlib import Path
from .common import RSIError, BudgetExceeded, Cancelled, Unavailable, atomic_json, canonical, digest
from .benchmark import validate, task_digest
from .catalog import catalog
from .engine import Engine, comparison
from .evaluation import efficiency_comparison


def validate_manifest(data, min_wins=2):
    if not isinstance(data,dict) or data.get('schema')!=1 or set(data)!={'schema','rounds','audit'}:
        raise RSIError('Study manifest requires schema=1, rounds and audit')
    rounds=data['rounds'];audit=data['audit']
    if not isinstance(rounds,list) or not 2<=len(rounds)<=20:raise RSIError('Study needs 2..20 precommitted rounds')
    seen=set();families=set()
    for index,tasks in enumerate([*rounds,audit]):
        validate(tasks)
        if index<len(rounds):
            if any(sum(t['split']==s for t in tasks)<min_wins for s in ('dev','validation','final')):
                raise RSIError('Study split too small')
        elif len(tasks)<min_wins or any(t['split']!='final' for t in tasks):
            raise RSIError('Audit must contain fresh final tasks')
        these={task_digest(t) for t in tasks};family={t['family'] for t in tasks}
        if len(these)!=len(tasks) or seen & these or families & family:
            raise RSIError('Study datasets overlap in tasks or families')
        seen.update(these);families.update(family)
    return data


def pilot_manifest():
    tasks=catalog()
    return validate_manifest({'schema':1,
        'rounds':[[t for t in tasks if lo<=int(t['id'].split('-')[-1])<=hi] for lo,hi in ((1,8),(9,16))],
        'audit':[t for t in tasks if t['split']=='final' and int(t['id'].split('-')[-1])>=17]})


def estimate(data,cfg):
    audit=len(data['audit'])*cfg['repeats']*cfg['steps_per_task']
    train=sum(3*sum(t['split']=='dev' for t in tasks)*cfg['steps_per_task']+1+
              2*sum(t['split'] in ('validation','final') for t in tasks)*cfg['repeats']*cfg['steps_per_task']+
              2*cfg['steps_per_task'] for tasks in data['rounds'])
    return {'rounds':len(data['rounds']),'max_calls_per_arm':train+audit,
            'audit_calls_reserved_per_arm':audit,
            'max_reserved_tokens_per_arm':(train+audit)*(cfg['context_tokens']+cfg['output_tokens']),
            'interpretation':'Upper bound, not measured consumption. Each arm has the same configured total budget.'}


class Study:
    def __init__(self,engine,engine_factory=None):
        self.engine=engine;self.factory=engine_factory or Engine
    def create_manifest(self,path):
        path=Path(path)
        if path.exists(): raise RSIError('Manifest already exists; refusing to overwrite it')
        data=pilot_manifest();atomic_json(path,data)
        return {'manifest':str(path.resolve()),'sha256':digest(canonical(data)),
                'estimate':estimate(data,self.engine.cfg),'warning':'Small authored pilot, not proof of real-world improvement.'}
    def run(self,path):
        data=validate_manifest(json.loads(Path(path).read_text(encoding='utf-8')),self.engine.cfg['min_new_wins'])
        cfg=dict(self.engine.cfg);planned=estimate(data,cfg)
        if len(data['rounds'])>cfg['max_generations']:raise RSIError('Study rounds exceed max_generations')
        audit_calls=planned['audit_calls_reserved_per_arm']
        audit_tokens=audit_calls*(cfg['context_tokens']+cfg['output_tokens'])
        if cfg['max_calls']<=audit_calls or cfg['max_tokens']<=audit_tokens:
            raise RSIError('Budget must cover the reserved audit plus training')
        if cfg['max_seconds']<2:raise RSIError('Study needs at least 2 seconds per arm')
        study_id='study-'+uuid.uuid4().hex[:12]
        directory=self.engine.root/'studies'/study_id
        directory.mkdir(parents=True)
        atomic_json(directory/'manifest.json',data)
        manifest_sha=digest(canonical(data))
        # The supervisor covers both sequential arms. Each arm also has its own
        # cumulative call/token/time budget across all rounds and the final audit.
        self.engine.cfg.update(max_calls=2*cfg['max_calls'],max_tokens=2*cfg['max_tokens'],max_seconds=2*cfg['max_seconds'])
        def work(rid,report):
            report.update(study_id=study_id,manifest_sha256=manifest_sha,estimate=planned,
                          active_agent_unchanged=True,arms={},usage={'n':0,'charged':0,'actual':None,'unknown':0})
            registry=self.engine.registry
            # Include the currently installed benchmark in the historical reuse check
            # for databases created before per-task holdout tracking was introduced.
            all_tasks=[t for tasks in data['rounds'] for t in tasks]+data['audit']
            with registry.connect() as c:
                used={r[0] for r in c.execute('SELECT digest FROM holdout_members')}
                old={r[0] for r in c.execute('SELECT digest FROM holdouts')}
            if used & {task_digest(t) for t in all_tasks}:raise RSIError('Study includes previously consumed holdout tasks')
            if self.engine.benchmark.final_digest() in old:
                prior={task_digest(t) for t in self.engine.benchmark.tasks('final')}
                if prior & {task_digest(t) for t in all_tasks}:raise RSIError('Study overlaps the consumed current benchmark')
            # Reserve every future holdout before any arm starts. Interrupted studies
            # retain these reservations; selectively retrying an exposed audit is forbidden.
            held=[t for t in all_tasks if t['split']=='final']
            registry.consume_holdout('study:'+manifest_sha,rid,held)
            report['environment']=dict(report['environment'],study_manifest_sha256=manifest_sha)
            baseline=self.engine.registry.active()
            report['initial_source_sha256']=baseline['sha']
            for name in ('fixed_author','recursive'):
                root=directory/name;atomic_json(root/'config.json',cfg)
                child=self.factory(root);child.init()
                # Exact same initial source, even when the user starts from an accepted agent.
                initial=child.registry.active()
                if initial['sha']!=baseline['sha']:
                    with child.registry.connect() as c:c.execute("DELETE FROM meta WHERE key='active'")
                    child.registry.add_artifact(baseline['source'])
                initial=child.registry.active()
                report['arms'][name]={'initial':initial['id'],'active':initial['id'],'rounds':[],
                    'usage':{'n':0,'charged':0,'actual':0,'unknown':0},'elapsed_seconds':0,
                    'accepted':0,'halted':False,'stagnation':0}
            def sync():
                usages=[v['usage'] for v in report['arms'].values()]
                report['usage']={k:sum(v[k] for v in usages) for k in ('n','charged','unknown')}
                report['usage']['actual']=sum(v['actual'] or 0 for v in usages) if all(v['actual'] is not None for v in usages) else None
                self.engine._checkpoint(rid,report)
                atomic_json(directory/'report.json',report)
            def child_engine(name,tasks,auditing=False):
                self.engine.registry.check(rid)
                # Check the saved commitment, not a mutable caller-owned input file.
                if digest(canonical(json.loads((directory/'manifest.json').read_text())))!=manifest_sha:
                    raise RSIError('Study commitment changed')
                arm=report['arms'][name];usage=arm['usage'];root=directory/name
                calls=cfg['max_calls']-usage['n']-(0 if auditing else audit_calls)
                tokens=cfg['max_tokens']-usage['charged']-(0 if auditing else audit_tokens)
                # Reserve one quarter of each arm's wall-time for its audit.
                seconds=int(cfg['max_seconds']*(1 if auditing else .75)-arm['elapsed_seconds'])
                if min(calls,tokens,seconds)<=0:raise BudgetExceeded('Arm budget exhausted')
                arm_cfg=dict(cfg,max_calls=calls,max_tokens=tokens,max_seconds=seconds,auto_promote=True)
                atomic_json(root/'config.json',arm_cfg);atomic_json(root/'benchmark.json',tasks)
                child=self.factory(root)
                child.registry.supervisor=lambda:registry.check(rid)
                child.required_environment=self.engine.fingerprint
                return child
            def account(name,result,elapsed):
                arm=report['arms'][name];arm['elapsed_seconds']+=elapsed;new=result.get('usage',{})
                for k in ('n','charged','unknown'):arm['usage'][k]+=new.get(k,0)
                if new.get('unknown') or arm['usage']['actual'] is None:arm['usage']['actual']=None
                else:arm['usage']['actual']+=(new.get('actual') or 0)
                arm['active']=result.get('active',arm['active']);sync()
            for index,tasks in enumerate(data['rounds']):
                for name in (('fixed_author','recursive') if index%2==0 else ('recursive','fixed_author')):
                    arm=report['arms'][name]
                    if arm['halted']:continue
                    try:child=child_engine(name,tasks)
                    except BudgetExceeded:
                        arm.update(halted=True,stop_reason='training_budget_reserved_for_audit');sync();continue
                    started=time.monotonic()
                    result=child.campaign(1,author_id=arm['initial'] if name=='fixed_author' else None)
                    arm['rounds'].append(result);account(name,result,time.monotonic()-started)
                    registry.check(rid)
                    if result['status']=='budget_exhausted':
                        arm.update(halted=True,stop_reason='training_budget_exhausted');continue
                    if result['status']!='complete':raise RSIError(f'{name} training incomplete: '+result['status'])
                    promoted=sum(g['status']=='promoted' for g in result['generations'])
                    arm['accepted']+=promoted;arm['stagnation']=0 if promoted else arm['stagnation']+1
                    if arm['stagnation']>=cfg['stagnation_limit']:arm.update(halted=True,stop_reason='stagnation')
                    sync()
            # Audit is never sent to either proposal generator. Score each final
            # agent with identical seeds and interleaved task order in one run.
            auditor=child_engine('fixed_author',data['audit'],True)
            recursive=child_engine('recursive',data['audit'],True)
            candidates={name:self.factory(directory/name).registry.active() for name in report['arms']}
            audit_runs={};rows={name:[] for name in report['arms']}
            agents={'fixed_author':auditor,'recursive':recursive}
            try:
                for name,child in agents.items():
                    audit_runs[name]=child.registry.new_run('study_audit',child.cfg)
                    child._prepare(audit_runs[name])
                for repeat in range(cfg['repeats']):
                    for index,task in enumerate(data['audit']):
                        for name in (('fixed_author','recursive') if (index+repeat)%2==0 else ('recursive','fixed_author')):
                            child=agents[name];started=time.monotonic()
                            remaining=cfg['max_seconds']-report['arms'][name]['elapsed_seconds']
                            if remaining<=0:raise BudgetExceeded('Arm audit time exhausted')
                            # Do not charge waiting for the other arm to this arm.
                            with child.registry.connect() as c:
                                c.execute('UPDATE runs SET deadline=? WHERE id=?',(time.time()+remaining,audit_runs[name]))
                            try:
                                child._check(audit_runs[name])
                                rows[name].append(child.runtime.solve(candidates[name],task,audit_runs[name],seed=repeat*1000+index*10))
                            finally:report['arms'][name]['elapsed_seconds']+=time.monotonic()-started
                report['comparison']=comparison(rows['fixed_author'],rows['recursive'],cfg['min_new_wins'])
                report['efficiency_comparison']=efficiency_comparison(rows['fixed_author'],rows['recursive'],cfg['min_token_saving_percent'])
                report['interpretation']='One paired pilot study; no causal or general RSI advantage is established.'
                report['audit_complete']=True
            finally:
                for name,arid in audit_runs.items():
                    child=agents[name];complete=len(rows[name])==len(data['audit'])*cfg['repeats']
                    result={'status':'complete' if complete else 'interrupted','results':rows[name],
                            'usage':child.registry.usage(arid),'active':child.registry.active()['id']}
                    child.registry.finish(arid,result['status'],result)
                    report['arms'][name]['audit']=result;account(name,result,0)
            sync()
        try:
            result=self.engine._run('study',work)
            result['study_id']=study_id
            atomic_json(directory/'report.json',result)
            return result
        finally:self.engine.cfg.update(cfg)
