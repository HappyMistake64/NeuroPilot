"""Trusted SQLite registry, immutable artifacts, quotas and audit chain."""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .common import RSIError, BudgetExceeded, Cancelled, canonical, digest

class Registry:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'registry.sqlite3'
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,parent TEXT,sha TEXT NOT NULL,source TEXT NOT NULL,status TEXT NOT NULL,hypothesis TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,kind TEXT,status TEXT,config TEXT,created REAL,deadline REAL,stopped INTEGER DEFAULT 0,report TEXT);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,kind TEXT,payload TEXT,previous TEXT,hash TEXT);
            CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,run_id TEXT,reserved INTEGER,actual INTEGER,status TEXT,details TEXT);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS holdouts(digest TEXT PRIMARY KEY,run_id TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS holdout_members(digest TEXT PRIMARY KEY,run_id TEXT);
            CREATE TABLE IF NOT EXISTS releases(seq INTEGER PRIMARY KEY AUTOINCREMENT,artifact TEXT,previous TEXT,created REAL,reason TEXT);
            ''')
    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=10); c.row_factory = sqlite3.Row
        try:
            c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA busy_timeout=10000')
            with c:
                yield c
        finally:
            c.close()
    def event(self, run, kind, payload):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            prev = c.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            previous = prev[0] if prev else ''
            value = canonical(payload); sha = digest(previous + canonical([run,kind,value]))
            c.execute('INSERT INTO events(run_id,kind,payload,previous,hash) VALUES(?,?,?,?,?)',(run,kind,value,previous,sha))
    def check_chain(self):
        previous = ''
        with self.connect() as c:
            for row in c.execute('SELECT * FROM events ORDER BY seq'):
                if row['previous'] != previous or row['hash'] != digest(previous+canonical([row['run_id'],row['kind'],row['payload']])):
                    return False
                previous = row['hash']
        return True
    def add_artifact(self, source, parent=None, hypothesis='baseline'):
        sha = digest(source); aid = 'agent-' + uuid.uuid4().hex[:12]
        if parent: self.artifact(parent)
        with self.connect() as c:
            c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(aid,parent,sha,source,'candidate' if parent else 'baseline',hypothesis,time.time()))
            if parent is None and not c.execute("SELECT value FROM meta WHERE key='active'").fetchone():
                c.execute("INSERT INTO meta VALUES('active',?)",(aid,))
        return aid
    def artifact(self, aid):
        with self.connect() as c: row = c.execute('SELECT * FROM artifacts WHERE id=?',(aid,)).fetchone()
        if row is None: raise RSIError('Unknown artifact')
        row = dict(row)
        if digest(row['source']) != row['sha']: raise RSIError('Artifact integrity failure')
        return row
    def active(self):
        with self.connect() as c: row = c.execute("SELECT value FROM meta WHERE key='active'").fetchone()
        if not row: raise RSIError('Run init first')
        return self.artifact(row[0])
    def set_status(self, aid, status):
        self.artifact(aid)
        with self.connect() as c: c.execute('UPDATE artifacts SET status=? WHERE id=?',(status,aid))
    def new_run(self, kind, cfg):
        rid='run-'+uuid.uuid4().hex[:12]; now=time.time()
        with self.connect() as c:
            c.execute('INSERT INTO runs(id,kind,status,config,created,deadline) VALUES(?,?,?,?,?,?)',(rid,kind,'running',canonical(cfg),now,now+cfg['max_seconds']))
        self.event(rid,'started',{'kind':kind,'config':cfg}); return rid
    def run(self, rid):
        with self.connect() as c: row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
        if not row: raise RSIError('Unknown run')
        result=dict(row); result['config']=json.loads(result['config'])
        result['report']=json.loads(result['report']) if result['report'] else None
        return result
    def check(self, rid):
        if getattr(self,'supervisor',None): self.supervisor()
        run=self.run(rid)
        if run['stopped']: raise Cancelled('Run stopped by user')
        if run['status'] != 'running': raise Cancelled('Run is no longer active')
        if time.time() >= run['deadline']: raise BudgetExceeded('Wall-time budget exceeded')
        return run
    def remaining(self,rid): return max(.01, self.check(rid)['deadline']-time.time())
    def stop(self,rid):
        self.run(rid)
        with self.connect() as c: c.execute('UPDATE runs SET stopped=1 WHERE id=?',(rid,))
        self.event(rid,'stop_requested',{})
    def finish(self,rid,status,report):
        with self.connect() as c: c.execute('UPDATE runs SET status=?,report=? WHERE id=?',(status,canonical(report),rid))
        self.event(rid,'finished',{'status':status})
    def reserve(self,rid,tokens):
        if type(tokens) is not int or tokens<=0: raise RSIError('Token reservation must be a positive integer')
        self.check(rid)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT config,stopped,status,deadline FROM runs WHERE id=?',(rid,)).fetchone()
            if row['stopped'] or row['status']!='running': raise Cancelled('Run stopped')
            if row['deadline']<=time.time(): raise BudgetExceeded('Wall-time budget exceeded')
            cfg=json.loads(row['config'])
            usage=c.execute('SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0) FROM calls WHERE run_id=?',(rid,)).fetchone()
            if usage[0]>=cfg['max_calls'] or usage[1]+tokens>cfg['max_tokens']: raise BudgetExceeded('Model quota exhausted')
            cid='call-'+uuid.uuid4().hex
            c.execute('INSERT INTO calls VALUES(?,?,?,?,?,?)',(cid,rid,tokens,None,'reserved','{}'))
            return cid
    def settle(self,cid,actual,details,status='complete'):
        if actual is not None and (type(actual) is not int or actual<0): actual=None
        with self.connect() as c: c.execute('UPDATE calls SET actual=?,details=?,status=? WHERE id=?',(actual,canonical(details),status,cid))
    def usage(self,rid):
        with self.connect() as c:
            r=c.execute('SELECT COUNT(*) n,COALESCE(SUM(COALESCE(actual,reserved)),0) charged,SUM(actual) actual,COALESCE(SUM(actual IS NULL),0) unknown FROM calls WHERE run_id=?',(rid,)).fetchone()
        return dict(r)
    def consume_holdout(self,sha,rid,tasks=None):
        try:
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute('INSERT INTO holdouts VALUES(?,?,?)',(sha,rid,time.time()))
                if tasks is not None:
                    from .benchmark import task_digest
                    c.executemany('INSERT INTO holdout_members VALUES(?,?)',[(task_digest(t),rid) for t in tasks])
        except sqlite3.IntegrityError as error: raise RSIError('Final set already consumed; import a genuinely fresh benchmark') from error
    def assert_fresh(self,tasks):
        from .benchmark import task_digest
        with self.connect() as c: used={r[0] for r in c.execute('SELECT digest FROM holdout_members')}
        if used & {task_digest(t) for t in tasks}:
            raise RSIError('Previously consumed holdout cannot be reused in any split')
    def promote(self,aid,expected_parent,reason):
        artifact=self.artifact(aid)
        if artifact['status']!='accepted': raise RSIError('Only accepted artifacts can be promoted')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE'); active=c.execute("SELECT value FROM meta WHERE key='active'").fetchone()[0]
            if active!=expected_parent or artifact['parent']!=active: raise RSIError('Active parent changed; new comparison required')
            c.execute("UPDATE meta SET value=? WHERE key='active'",(aid,))
            c.execute('INSERT INTO releases(artifact,previous,created,reason) VALUES(?,?,?,?)',(aid,active,time.time(),reason))
    def rollback(self):
        active=self.active()
        parent_id=active['parent']
        if not parent_id: raise RSIError('No previous release')
        parent=self.artifact(parent_id)
        if parent['status'] not in ('baseline','accepted'): raise RSIError('Parent is not a known-good version')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            current=c.execute("SELECT value FROM meta WHERE key='active'").fetchone()[0]
            if current!=active['id']: raise RSIError('Active version changed')
            c.execute("UPDATE meta SET value=? WHERE key='active'",(parent_id,))
            c.execute('INSERT INTO releases(artifact,previous,created,reason) VALUES(?,?,?,?)',(parent_id,active['id'],time.time(),'rollback'))
        self.event(None,'rollback',{'from':active['id'],'to':parent_id}); return parent_id
    def summary(self):
        with self.connect() as c:
            artifacts=[dict(r) for r in c.execute('SELECT id,parent,sha,status,hypothesis,created FROM artifacts ORDER BY created')]
            runs=[dict(r) for r in c.execute('SELECT id,kind,status,created,stopped FROM runs ORDER BY created DESC LIMIT 100')]
        try: active=self.active()['id']
        except RSIError: active=None
        return {'active':active,'artifacts':artifacts,'runs':runs,'audit_chain_valid':self.check_chain()}
    @contextmanager
    def exclusive(self):
        # OS lock is released on crash; no stale boolean lock in the database.
        import fcntl
        with (self.root/'experiment.lock').open('w') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error: raise RSIError('Another experiment is running') from error
            try: yield
            finally: fcntl.flock(lock,fcntl.LOCK_UN)
