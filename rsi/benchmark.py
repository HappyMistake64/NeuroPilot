"""Trusted benchmark storage; expected outputs never enter candidate sandboxes."""
import json
from pathlib import Path
from .common import RSIError, canonical, digest, atomic_json
from .catalog import catalog


def task_digest(task):
    return digest(canonical({k:task[k] for k in ('instruction','files','public','hidden')}))

def validate(tasks):
    if not isinstance(tasks,list) or not 1<=len(tasks)<=1000: raise RSIError('Expected 1..1000 tasks')
    ids=set(); families={};content=set()
    for task in tasks:
        if not isinstance(task,dict): raise RSIError('Invalid task')
        tid=task.get('id'); split=task.get('split'); family=task.get('family')
        if not isinstance(tid,str) or not tid or tid in ids or split not in ('dev','validation','final'): raise RSIError('Invalid ID/split')
        if not isinstance(family,str) or not family: raise RSIError('Missing family')
        if family in families and families[family]!=split: raise RSIError('Task-family leakage between splits')
        families[family]=split;ids.add(tid)
        if not isinstance(task.get('instruction'),str) or not 1<=len(task['instruction'])<=10000: raise RSIError('Invalid instruction')
        if not isinstance(task.get('files'),dict) or set(task['files'])!={'solution.py'} or not isinstance(task['files']['solution.py'],str) or len(task['files']['solution.py'])>20000: raise RSIError('Pilot supports solution.py only')
        if task.get('entrypoint')!='solve': raise RSIError('Pilot entrypoint must be solve')
        for kind in ('public','hidden'):
            checks=task.get(kind)
            if not isinstance(checks,list) or not 1<=len(checks)<=100: raise RSIError('Missing checks')
            for check in checks:
                if not isinstance(check,dict) or not isinstance(check.get('args'),list) or 'expected' not in check: raise RSIError('Invalid check')
                canonical(check)
        canonical(task)
        fingerprint=task_digest(task)
        if fingerprint in content:raise RSIError('Duplicate task content in benchmark')
        content.add(fingerprint)
    return tasks

class Benchmark:
    def __init__(self,root): self.path=Path(root)/'benchmark.json'
    def init(self):
        if not self.path.exists(): atomic_json(self.path,validate(catalog()))
        return self.info()
    def load(self):
        if not self.path.exists(): raise RSIError('Run init first')
        return validate(json.loads(self.path.read_text(encoding='utf-8')))
    def tasks(self,split): return [t for t in self.load() if t['split']==split]
    def info(self):
        tasks=self.load()
        return {'sha256':digest(canonical(tasks)),'counts':{s:sum(t['split']==s for t in tasks) for s in ('dev','validation','final')},'kind':'authored synthetic pilot; not SWE-bench'}
    def import_file(self,path):
        tasks=validate(json.loads(Path(path).read_text(encoding='utf-8')))
        atomic_json(self.path,tasks); return self.info()
    def final_digest(self):
        # Ignore cosmetic IDs/names to prevent reusing the same holdout under a new label.
        content=[{k:t[k] for k in ('instruction','files','public','hidden')} for t in self.tasks('final')]
        return digest(canonical(sorted(content,key=canonical)))
