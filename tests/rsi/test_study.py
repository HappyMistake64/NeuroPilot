"""Explicit fixtures verify controls; never evidence of actual model improvement."""
import copy
import json
from pathlib import Path
import pytest
from rsi.common import DEFAULTS, RSIError, atomic_json
from rsi.catalog import catalog
from rsi.engine import Engine
from rsi.registry import Registry
from rsi.evaluation import efficiency_comparison
from rsi.study import Study, validate_manifest, pilot_manifest, estimate
from test_integration import FixtureSandbox, FixtureProvider, BASELINE, CANDIDATE, CANDIDATE2


def measurements(values,tokens):
    return [{'task':str(i),'seed':repeat,'resolved':ok,'usage':{'actual_tokens':tokens},'elapsed':1}
            for i,ok in enumerate(values) for repeat in range(3)]


def test_efficiency_requires_same_nonzero_successes_and_known_counts():
    a=measurements([True,False],100);b=measurements([True,False],85)
    result=efficiency_comparison(a,b)
    assert result['gate_passed'] and result['saving_percent']==15
    assert not efficiency_comparison(a,measurements([True,False],86))['gate_passed']
    assert not efficiency_comparison(a,measurements([False,False],1))['gate_passed']
    assert not efficiency_comparison(measurements([False],100),measurements([False],1))['gate_passed']
    b[0]['usage']['actual_tokens']=None
    result=efficiency_comparison(a,b)
    assert not result['gate_passed'] and result['candidate_tokens'] is None


def test_efficiency_rejects_unpaired_and_unstable_trials():
    a=measurements([True],100);b=measurements([True],50)
    with pytest.raises(RSIError):efficiency_comparison(a,b[:-1])
    b[0]['seed']=1
    with pytest.raises(RSIError):efficiency_comparison(a,b)
    a[0]['resolved']=False;b=copy.deepcopy(a)
    for r in b:r['usage']['actual_tokens']=1
    assert not efficiency_comparison(a,b)['gate_passed']


def test_manifest_prevents_relabelled_or_family_overlap():
    data=pilot_manifest();assert estimate(data,DEFAULTS)['max_calls_per_arm']==770
    duplicate=copy.deepcopy(data['rounds'][0][0]);duplicate['id']='renamed';duplicate['family']='renamed'
    data['rounds'][1].append(duplicate)
    with pytest.raises(RSIError,match='overlap'):validate_manifest(data)
    data=pilot_manifest();data['rounds'][1][0]['family']=data['rounds'][0][0]['family']
    with pytest.raises(RSIError,match='overlap'):validate_manifest(data)


def small_manifest():
    tasks=catalog()
    return {'schema':1,'rounds':[[t for t in tasks if lo<=int(t['id'].split('-')[-1])<=hi]
                               for lo,hi in ((1,2),(3,4))],
            'audit':[t for t in tasks if t['split']=='final' and 5<=int(t['id'].split('-')[-1])<=6]}


class AuthorFixture(FixtureProvider):
    def complete(self,messages,rid,seed=0):
        payload=json.loads(messages[-1]['content'])
        response=super().complete(messages,rid,seed)
        if payload['mode']=='propose' and payload['fixture_level']==0:
            response['strategy_source']=CANDIDATE
        if payload['mode']=='solve' and payload['fixture_level']==2:
            task=next(t for t in catalog() if t['id']==payload['task']['id'])
            response={'actions':[{'tool':'write_file','path':'solution.py',
                'sha256':payload['files']['solution.py']['sha256'],'content':task['reference']},{'tool':'finish'}]}
        return response


@pytest.fixture
def study_setup(tmp_path):
    providers=[]
    def factory(root):
        provider=AuthorFixture(Registry(root));providers.append(provider)
        return Engine(root,provider,FixtureSandbox())
    e=factory(tmp_path/'state');e.init();e.cfg.update(max_calls=1000,max_tokens=2000000,max_seconds=120)
    path=tmp_path/'manifest.json';atomic_json(path,small_manifest())
    return e,Study(e,factory),path,providers


def test_two_arm_recursive_lineage_fair_audit_and_no_production_change(study_setup):
    e,study,path,providers=study_setup;old=e.registry.active()['id'];budget=dict(e.cfg)
    result=study.run(path)
    assert result['status']=='complete',result
    assert result['audit_complete'] and not result['actual_rsi_improvement_proven']
    arms=result['arms'];assert arms['fixed_author']['accepted']==1 and arms['recursive']['accepted']==2
    for name,arm in arms.items():
        assert arm['usage']['n']<=budget['max_calls'] and arm['usage']['charged']<=budget['max_tokens']
        assert len(arm['audit']['results'])==6
        assert arm['rounds'][1]['generations'][0]['author']==(
            arm['initial'] if name=='fixed_author' else arm['rounds'][0]['active'])
    assert result['comparison']['gate_passed']
    assert e.registry.active()['id']==old and e.cfg==budget
    assert result['usage']['n']==sum(a['usage']['n'] for a in arms.values())
    for provider in providers:
        for messages in provider.requests:
            payload=json.loads(messages[-1]['content'])
            if payload['mode']=='propose':assert all(x['task'].startswith('dev-') for x in payload['evidence'])
    again=study.run(path)
    assert again['status']=='failed' and 'consumed' in again['error']


def test_cumulative_budget_preserves_audit(study_setup):
    e,study,path,_=study_setup;e.cfg.update(max_calls=28,max_tokens=400000)
    result=study.run(path)
    assert result['status']=='complete',result
    assert result['audit_complete']
    assert all(a['usage']['n']<=28 for a in result['arms'].values())
    assert any(a['halted'] for a in result['arms'].values())


def test_insufficient_budget_does_not_start(study_setup):
    e,study,path,_=study_setup;e.cfg['max_calls']=1
    with pytest.raises(RSIError,match='reserved audit'):study.run(path)
    assert not e.registry.summary()['runs']


def test_study_stop_propagates_into_child(study_setup,monkeypatch):
    e,study,path,_=study_setup;original=AuthorFixture.complete
    def stop(self,messages,rid,seed=0):
        running=next(r for r in e.registry.summary()['runs'] if r['kind']=='study')
        e.registry.stop(running['id'])
        return original(self,messages,rid,seed)
    monkeypatch.setattr(AuthorFixture,'complete',stop)
    result=study.run(path)
    assert result['status']=='stopped',result
    assert not result.get('audit_complete')
    assert e.registry.active()['status']=='baseline'


def test_task_level_holdout_prevents_repacked_subset(tmp_path):
    r=Registry(tmp_path);tasks=[t for t in catalog() if t['split']=='final']
    r.consume_holdout('full','first',tasks)
    relabelled=copy.deepcopy(tasks[:2]);relabelled[0]['id']='other'
    with pytest.raises(RSIError):r.consume_holdout('subset','second',relabelled)
    with r.connect() as c:assert c.execute('SELECT 1 FROM holdouts WHERE digest=?',('subset',)).fetchone() is None

class EfficiencyFixture(FixtureProvider):
    unknown=False
    def complete(self,messages,rid,seed=0):
        payload=json.loads(messages[-1]['content']);result=super().complete(messages,rid,seed)
        with self.registry.connect() as c:cid=c.execute('SELECT id FROM calls WHERE run_id=? ORDER BY rowid DESC LIMIT 1',(rid,)).fetchone()[0]
        self.registry.settle(cid,None if self.unknown else (60 if payload['fixture_candidate'] else 100),{'fixture':True})
        if payload['mode']=='solve':
            task=next(t for t in catalog() if t['id']==payload['task']['id'])
            return {'actions':[{'tool':'write_file','path':'solution.py','sha256':payload['files']['solution.py']['sha256'],'content':task['reference']},{'tool':'finish'}]}
        return result


def test_efficiency_only_release_is_never_labelled_capability_gain(tmp_path):
    provider=EfficiencyFixture(Registry(tmp_path));e=Engine(tmp_path,provider,FixtureSandbox());e.init()
    atomic_json(e.benchmark.path,[t for t in catalog() if int(t['id'].split('-')[-1])<=2])
    result=e.campaign(1)
    assert result['status']=='complete',result
    assert result['generations'][0]['gain_kind']=='efficiency'
    assert result['pilot_efficiency_gain_confirmed'] and 'pilot_capability_gain_confirmed' not in result
    assert result['generations'][0]['final']['efficiency']['saving_percent']==40
    aid=result['generations'][0]['candidate']
    assert e.activate(aid)['status']=='complete'


def test_unknown_telemetry_cannot_release_cheaper_candidate(tmp_path):
    provider=EfficiencyFixture(Registry(tmp_path));provider.unknown=True
    e=Engine(tmp_path,provider,FixtureSandbox());e.init()
    atomic_json(e.benchmark.path,[t for t in catalog() if int(t['id'].split('-')[-1])<=2])
    result=e.campaign(1)
    assert result['generations'][0]['status']=='rejected_development'
    assert not result['generations'][0]['development']['efficiency']['telemetry_complete']
    assert 'pilot_efficiency_gain_confirmed' not in result
