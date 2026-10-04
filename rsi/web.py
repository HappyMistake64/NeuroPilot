"""Same-origin local dashboard for the RSI controller."""
import os
import difflib
import json
import threading
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory
from .engine import Engine
from .common import RSIError, atomic_json
from .study import Study, validate_manifest, estimate

blueprint=Blueprint('rsi',__name__)
_job_lock=threading.Lock()
_last_job={}

def engine():
    root=os.environ.get('NEUROPILOT_RSI_STATE',str(Path(__file__).resolve().parents[1]/'rsi_state'))
    return Engine(root)

@blueprint.route('/rsi')
def index(): return send_from_directory(Path(__file__).parent/'public','index.html')

@blueprint.route('/rsi/app.js')
def script(): return send_from_directory(Path(__file__).parent/'public','app.js')

@blueprint.route('/rsi/api/status')
def status():
    obj=engine();result=obj.status();result['job']=dict(_last_job)
    result['limits']={k:obj.cfg[k] for k in ('max_calls','max_tokens','max_seconds','max_generations')}
    result['gates']={k:obj.cfg[k] for k in ('allow_efficiency','min_token_saving_percent','min_new_wins','repeats')}
    manifest=obj.root/'study_manifest.json'
    if manifest.exists():
        try:result['study_plan']=estimate(validate_manifest(json.loads(manifest.read_text()),obj.cfg['min_new_wins']),obj.cfg)
        except (RSIError,ValueError):result['study_plan']={'error':'Invalid study manifest'}
    return jsonify(result)

@blueprint.route('/rsi/api/openai/status')
def openai_status():
    from .openai_auth import Accounts, login_status
    try:
        accounts=Accounts();result=accounts.status();result['login']=login_status(accounts)
        return jsonify(result)
    except (RSIError,OSError) as error:return jsonify(error=str(error)),400

@blueprint.route('/rsi/api/openai/<action>',methods=['POST'])
def openai_action(action):
    from .openai_auth import Accounts, begin_login, cancel_login
    from .openai_provider import ChatGPT
    body=request.get_json()
    if not isinstance(body,dict):return jsonify(error='Expected JSON object'),400
    try:
        obj=engine();accounts=Accounts()
        with obj.registry.exclusive():
            if action=='login':
                cid=body.get('account')
                if cid is not None and not isinstance(cid,str):raise RSIError('Invalid account')
                login=begin_login(accounts,cid)
                return jsonify(url=login.url,status='waiting',expires_in=600)
            if action=='cancel': cancel_login(accounts);return jsonify(cancelled=True)
            if action=='logout':
                cancel_login(accounts)
                return jsonify(accounts.logout())
            if action=='select':
                cid=body.get('account')
                if not isinstance(cid,str):raise RSIError('Invalid account')
                accounts.select(cid)
                # Force deliberate model selection for the newly selected account.
                cfg=dict(obj.cfg,openai_model='');atomic_json(obj.root/'config.json',cfg)
                return jsonify(selected=cid)
            if action=='models':return jsonify(models=ChatGPT(obj.cfg,obj.registry,accounts).models())
            if action=='configure':
                model=body.get('model')
                if not isinstance(model,str) or model not in {m['id'] for m in ChatGPT(obj.cfg,obj.registry,accounts).models()}:raise RSIError('Vyber model z aktuálního seznamu.')
                cfg=dict(obj.cfg,provider='chatgpt',openai_model=model)
                atomic_json(obj.root/'config.json',cfg)
                return jsonify(provider='chatgpt',model=model)
            if action=='ollama':
                atomic_json(obj.root/'config.json',dict(obj.cfg,provider='ollama'))
                return jsonify(provider='ollama')
            return jsonify(error='Unknown OpenAI action'),400
    except (RSIError,OSError,ValueError) as error:return jsonify(error=str(error)),400

@blueprint.after_request
def private_responses(response):
    if request.path.startswith('/rsi/api/openai/'):
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
    return response

@blueprint.route('/rsi/api/run/<rid>')
def report(rid):
    try: return jsonify(engine().registry.run(rid))
    except RSIError as error: return jsonify(error=str(error)),404

@blueprint.route('/rsi/api/artifact/<aid>')
def artifact(aid):
    try:
        obj=engine();item=obj.registry.artifact(aid)
        parent=obj.registry.artifact(item['parent']) if item['parent'] else None
        item['diff']=''.join(difflib.unified_diff((parent['source'] if parent else '').splitlines(True),item['source'].splitlines(True),fromfile='parent/strategy.py',tofile='candidate/strategy.py'))
        return jsonify(item)
    except RSIError as error:return jsonify(error=str(error)),404

@blueprint.route('/rsi/api/init',methods=['POST'])
def init():
    try:
        obj=engine()
        with obj.registry.exclusive(): return jsonify(obj.init())
    except RSIError as error:return jsonify(error=str(error)),409

@blueprint.route('/rsi/api/stop/<rid>',methods=['POST'])
def stop(rid):
    try: engine().registry.stop(rid);return jsonify(ok=True)
    except RSIError as error:return jsonify(error=str(error)),404

@blueprint.route('/rsi/api/job',methods=['POST'])
def job():
    body=request.get_json()
    if not isinstance(body,dict) or body.get('kind') not in ('doctor','provider_check','baseline','campaign','activate','rollback','study_prepare','study'):
        return jsonify(error='Unknown job'),400
    if body['kind']=='activate' and not isinstance(body.get('artifact'),str):return jsonify(error='Artifact required'),400
    if not _job_lock.acquire(blocking=False): return jsonify(error='A job is already running'),409
    # Copy inputs before starting the worker; request context is not retained.
    kind=body['kind'];aid=body.get('artifact')
    _last_job.clear();_last_job.update(kind=kind,status='running')
    def work():
        try:
            obj=engine()
            if kind=='doctor': result=obj.doctor()
            elif kind=='provider_check': result=obj.provider_check()
            elif kind=='baseline': result=obj.baseline(limit=10)
            elif kind=='campaign': result=obj.campaign(generations=1)
            elif kind=='activate': result=obj.activate(aid)
            elif kind=='study_prepare':
                with obj.registry.exclusive():
                    path=obj.root/'study_manifest.json'
                    if path.exists():result={'estimate':estimate(validate_manifest(json.loads(path.read_text()),obj.cfg['min_new_wins']),obj.cfg)}
                    else:result=Study(obj).create_manifest(path)
            elif kind=='study': result=Study(obj).run(obj.root/'study_manifest.json')
            else:
                with obj.registry.exclusive():result={'active':obj.registry.rollback()}
            _last_job.update(status='finished',result=result)
        except Exception as error: _last_job.update(status='failed',error=str(error))
        finally: _job_lock.release()
    threading.Thread(target=work,name='rsi-job',daemon=True).start()
    return jsonify(started=kind),202
