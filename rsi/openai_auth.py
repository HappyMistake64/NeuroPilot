"""Official public-client ChatGPT plan OAuth. Credentials never enter RSI state/logs.

Protocol: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
This local desktop flow deliberately uses its own registration, not Codex tokens.
"""
import base64
import fcntl
import hashlib
import json
import math
import os
import secrets
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from .common import RSIError, Unavailable, atomic_json, digest, canonical

ISSUER='https://auth.openai.com'
RESOURCE='https://api.openai.com/v1'
AUTHORIZE=ISSUER+'/api/accounts/authorize'
TOKEN=ISSUER+'/api/accounts/oauth/token'
SCOPE='openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
PLAN_SCOPE='chatgpt.tokens.use.direct'

class ServiceError(Unavailable):
    def __init__(self,code='network_error',status=None):
        self.code=code;self.status=status
        super().__init__('OpenAI: '+code+'. Zkontroluj přihlášení a oprávnění v ChatGPT.')

ERROR_CODES={'invalid_grant','invalid_client','invalid_token','access_denied',
    'subscription_sharing_usage_limit_exceeded','subscription_sharing_usage_unavailable',
    'insufficient_scope','rate_limit_exceeded','server_error','temporarily_unavailable'}

def safe_code(value):
    return value if isinstance(value,str) and value in ERROR_CODES else 'request_failed'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ServiceError('redirect_rejected')

def opener():
    # Managed cloud runtimes require their inherited proxy and CA trust.
    # Keep redirect rejection: bearer tokens must not follow another endpoint.
    return build_opener(ProxyHandler(),NoRedirect())

def official_url(url,host):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!=host or p.port not in (None,443) or p.username or p.password or p.fragment:
        raise RSIError('Invalid OpenAI service endpoint')
    return url

def request_json(url,form=None,token=None,empty=False):
    official_url(url,'api.openai.com' if url.startswith(RESOURCE+'/') else 'auth.openai.com')
    headers={'Accept':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    data=None
    if form is not None:
        data=urlencode(form).encode();headers['Content-Type']='application/x-www-form-urlencoded'
    try:
        with opener().open(Request(url,data=data,headers=headers),timeout=15) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise ServiceError('response_too_large')
            if empty and not raw: return {}
            result=json.loads(raw)
            if not isinstance(result,dict): raise ServiceError('invalid_response')
            return result
    except HTTPError as error:
        try:
            body=json.loads(error.read(4096));value=body.get('error')
            code=value.get('code') if isinstance(value,dict) else value
        except (ValueError,AttributeError): code=None
        raise ServiceError(safe_code(code),error.code) from None
    except (URLError,OSError,ValueError): raise ServiceError() from None

def validate_identity(token,client_id,nonce=None):
    try: import jwt
    except ImportError: raise Unavailable('Nainstaluj requirements.txt (PyJWT[crypto]).') from None
    discovery=request_json(ISSUER+'/.well-known/openid-configuration')
    if discovery.get('issuer')!=ISSUER: raise RSIError('OIDC issuer mismatch')
    jwks=request_json(official_url(discovery.get('jwks_uri',''),'auth.openai.com'))
    try:
        header=jwt.get_unverified_header(token)
        if header.get('alg') not in ('RS256','ES256'): raise ValueError('algorithm')
        keys=[key for key in jwks.get('keys',[]) if key.get('kid')==header.get('kid')]
        if len(keys)!=1 or keys[0].get('use','sig')!='sig': raise ValueError('key')
        key=jwt.PyJWK.from_dict(keys[0],algorithm=header['alg'])
        claims=jwt.decode(token,key.key,algorithms=[header['alg']],audience=client_id,issuer=ISSUER,
                          leeway=5,options={'require':['sub','exp','iat','iss','aud']})
        if not isinstance(claims['sub'],str) or not claims['sub']: raise ValueError('subject')
        if nonce is not None and claims.get('nonce')!=nonce: raise ValueError('nonce')
        if isinstance(claims['aud'],list) and len(claims['aud'])>1 and claims.get('azp')!=client_id: raise ValueError('azp')
        return claims
    except (jwt.PyJWTError,ValueError,KeyError,TypeError): raise RSIError('OpenAI ID token validation failed') from None

class Accounts:
    def __init__(self,root=None):
        self.root=Path(root or os.environ.get('NEUROPILOT_OPENAI_AUTH_DIR',Path.home()/'.config'/'neuropilot'/'openai')).expanduser()
        self.path=self.root/'accounts.json'

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.root.is_symlink() or self.path.is_symlink(): raise RSIError('Symlink credential store rejected')
        os.chmod(self.root,0o700)
        fd=os.open(self.root/'auth.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(lock,fcntl.LOCK_UN)

    def _read(self):
        if not self.path.exists(): return {'host_id':'urn:uuid:'+str(uuid.uuid4()),'active':None,'accounts':{}}
        os.chmod(self.path,0o600)
        try:
            data=json.loads(self.path.read_text())
            if not isinstance(data,dict) or not isinstance(data.get('accounts'),dict): raise ValueError()
            return data
        except (ValueError,TypeError): raise RSIError('Invalid OpenAI credential store') from None

    def _save(self,data): atomic_json(self.path,data);os.chmod(self.path,0o600)

    def status(self):
        with self.locked():
            data=self._read()
            if not self.path.exists(): self._save(data)
            rows=[{'id':cid,'email':a.get('email',''),'signed_in':bool(a.get('refresh_token')),
                   'plan_permission':PLAN_SCOPE in a.get('scopes',[])} for cid,a in data['accounts'].items()]
            return {'active':data['active'],'accounts':rows,'inference_verified':False}

    def import_registration(self,source,client_id,forbidden_roots=()):
        """Import one native NeuroPilot registration, never the source host ID.

        The caller transfers the file over a secure channel. No Codex credential
        discovery, token arguments, or credential contents in returned results.
        """
        if not isinstance(client_id,str) or not client_id.startswith('oaiapp_') or len(client_id)>250:
            raise RSIError('Invalid issued OpenAI client ID')
        source=Path(source).expanduser()
        roots=[Path(__file__).resolve().parents[1],*(Path(p).resolve() for p in forbidden_roots)]
        if any(p.resolve().is_relative_to(root) for p in (source,self.root) for root in roots):
            raise RSIError('Credentials must stay outside the project and RSI state')
        # Persist the destination host before reading or validating an import.
        self.status()
        try:
            fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
                    raise RSIError('Import requires an owner-only regular credential file (0600)')
                raw=stream.read(1_000_001)
            if len(raw)>1_000_000: raise ValueError()
            imported=json.loads(raw)
            record=imported['accounts'][client_id]
            if not isinstance(record,dict) or record.get('client_id')!=client_id or record.get('issuer')!=ISSUER:
                raise ValueError()
            for key in ('subject','access_token','refresh_token','id_token'):
                if not isinstance(record.get(key),str) or not record[key]: raise ValueError()
            scopes=record.get('scopes')
            if not isinstance(scopes,list) or not all(isinstance(s,str) for s in scopes) or PLAN_SCOPE not in scopes:
                raise ValueError()
            expiry=record.get('expires_at')
            if type(expiry) not in (int,float) or not math.isfinite(expiry) or expiry<=0: raise ValueError()
        except (OSError,ValueError,KeyError,TypeError):
            raise RSIError('Invalid protected NeuroPilot import file; no credentials imported') from None
        # A fresh local sign-in is required if the retained ID token has expired.
        claims=validate_identity(record['id_token'],client_id)
        if claims['sub']!=record['subject']: raise RSIError('Imported ChatGPT identity mismatch')
        clean={key:record[key] for key in ('client_id','issuer','subject','access_token','refresh_token','id_token','scopes','expires_at')}
        clean['email']=claims.get('email','')
        with self.locked():
            data=self._read();old=data['accounts'].get(client_id)
            if old and old.get('subject') not in (None,clean['subject']):
                raise RSIError('ChatGPT account identity changed')
            data['accounts'][client_id]=clean;data['active']=client_id;self._save(data)
        return {'imported':True,'inference_verified':False,'host_id_preserved':True}

    def prepare(self,redirect_uri,client_id=None):
        with self.locked():
            data=self._read();self._save(data)
            old=data['accounts'].get(client_id) if client_id else None
            if client_id and old is None: raise RSIError('Unknown ChatGPT account')
            verifier=secrets.token_urlsafe(48)
            pending={'state':secrets.token_urlsafe(32),'nonce':secrets.token_urlsafe(32),
                     'verifier':verifier,'redirect_uri':redirect_uri,'client_id':client_id,
                     'subject':old['subject'] if old else None,'expires':time.monotonic()+600}
            query={'client_id':client_id or 'dynamic_agent_client','ext_agent_host_id':data['host_id'],
                   'response_type':'code','redirect_uri':redirect_uri,'scope':SCOPE,'resource':RESOURCE,
                   'state':pending['state'],'nonce':pending['nonce'],'code_challenge_method':'S256',
                   'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
            if not client_id: query['agent_name_hint']='NeuroPilot'
            # Omit optional ID-token hints: authorization URLs contain no credentials.
            return pending,AUTHORIZE+'?'+urlencode(query)

    def accept(self,pending,params):
        if time.monotonic()>pending['expires'] or not secrets.compare_digest(params.get('state',''),pending['state']):
            raise RSIError('Invalid or expired OAuth state')
        if params.get('error'): raise ServiceError(safe_code(params['error']))
        cid=params.get('client_id') or pending['client_id']
        if not isinstance(cid,str) or not cid.startswith('oaiapp_') or len(cid)>250: raise RSIError('Missing issued OpenAI client ID')
        if pending['client_id'] and cid!=pending['client_id']: raise RSIError('OpenAI registration changed')
        code=params.get('code')
        if not isinstance(code,str) or not 1<=len(code)<=8192: raise RSIError('Missing OAuth code')
        with self.locked():
            data=self._read()
            # Retain registration even if the authorization code expires. It is not
            # authenticated and cannot become active until ID-token validation.
            if cid not in data['accounts']:
                data['accounts'][cid]={'client_id':cid,'issuer':ISSUER,'subject':None,'email':''}
                self._save(data)
            tokens=request_json(TOKEN,{'grant_type':'authorization_code','client_id':cid,'code':code,
                'code_verifier':pending['verifier'],'redirect_uri':pending['redirect_uri'],'resource':RESOURCE})
            claims=validate_identity(tokens.get('id_token'),cid,pending['nonce'])
            old=data['accounts'].get(cid)
            expected=pending['subject'] or (old and old['subject'])
            if expected and claims['sub']!=expected: raise RSIError('ChatGPT account identity changed')
            record={'subject':claims['sub'],'issuer':ISSUER,'client_id':cid,'email':claims.get('email','')}
            self._tokens(record,tokens)
            data['accounts'][cid]=record;data['active']=cid;self._save(data)

    def _tokens(self,record,tokens):
        for key in ('access_token','refresh_token'):
            if not isinstance(tokens.get(key),str) or not tokens[key]: raise RSIError('Incomplete OpenAI token response')
        if str(tokens.get('token_type','')).lower()!='bearer': raise RSIError('Invalid OpenAI token type')
        expires=tokens.get('expires_in')
        if type(expires) is not int or not 1<=expires<=86400: raise RSIError('Invalid OpenAI token expiry')
        scopes=tokens.get('scope')
        if scopes is None: scopes=' '.join(record.get('scopes',[]))
        if not isinstance(scopes,str) or PLAN_SCOPE not in scopes.split(): raise Unavailable('Povol využití předplatného v přihlášení ChatGPT.')
        record.update(access_token=tokens['access_token'],refresh_token=tokens['refresh_token'],
                      expires_at=time.time()+expires,scopes=scopes.split())
        if tokens.get('id_token'): record['id_token']=tokens['id_token']

    def credentials(self):
        with self.locked():
            data=self._read();record=data['accounts'].get(data['active'])
            if not record or not record.get('refresh_token'): raise Unavailable('Nejdřív se přihlas přes Continue with ChatGPT.')
            if record.get('expires_at',0)<=time.time()+60:
                try:
                    tokens=request_json(TOKEN,{'grant_type':'refresh_token','client_id':record['client_id'],
                        'refresh_token':record['refresh_token'],'resource':RESOURCE})
                    if tokens.get('id_token'):
                        claims=validate_identity(tokens['id_token'],record['client_id'])
                        if claims['sub']!=record['subject']: raise RSIError('Refreshed ChatGPT identity changed')
                    self._tokens(record,tokens);self._save(data)
                except ServiceError as error:
                    if error.code=='invalid_grant':
                        for key in ('access_token','refresh_token','id_token'): record.pop(key,None)
                        self._save(data)
                    raise
            if PLAN_SCOPE not in record.get('scopes',[]): raise Unavailable('ChatGPT plan permission missing')
            identity=digest(canonical([record['issuer'],record['client_id'],record['subject']]))
            return record['access_token'],identity

    def select(self,cid):
        with self.locked():
            data=self._read()
            if cid not in data['accounts'] or not data['accounts'][cid].get('refresh_token'): raise RSIError('Přihlas tento účet znovu.')
            data['active']=cid;self._save(data)

    def logout(self,cid=None):
        with self.locked():
            data=self._read();cid=cid or data['active'];record=data['accounts'].get(cid)
            confirmed=False
            if record:
                if record.get('refresh_token'):
                    try:
                        discovery=request_json(ISSUER+'/.well-known/openid-configuration')
                        endpoint=official_url(discovery.get('revocation_endpoint',''),'auth.openai.com')
                        request_json(endpoint,{'token':record['refresh_token'],'token_type_hint':'refresh_token','client_id':cid},empty=True)
                        confirmed=True
                    except (RSIError,OSError): pass
                for key in ('access_token','refresh_token','id_token','expires_at'): record.pop(key,None)
                if data['active']==cid: data['active']=None
                self._save(data)
            return {'signed_out':True,'remote_revocation_confirmed':confirmed,
                    'message':'Odhlášeno.' if confirmed else 'Místně odhlášeno. Vzdálené odvolání nebylo potvrzeno; přístup lze zrušit v nastavení ChatGPT.'}

class Login:
    """One bounded, single-use loopback listener; no callback URL in access logs."""
    def __init__(self,accounts,client_id=None):
        self.done=threading.Event();self.result={'status':'waiting'};self.guard=threading.Lock();self.consumed=False
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                code=400;message='Neplatný požadavek.'
                try:
                    if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}' or len(self.path)>16000: raise RSIError('Invalid callback host')
                    parsed=urlsplit(self.path)
                    if parsed.path!='/auth/callback': raise RSIError('Invalid callback path')
                    values=parse_qs(parsed.query,keep_blank_values=True,max_num_fields=12)
                    if any(len(v)!=1 for v in values.values()): raise RSIError('Duplicate callback parameter')
                    params={k:v[0] for k,v in values.items()}
                    with owner.guard:
                        if owner.consumed or owner.done.is_set(): raise RSIError('OAuth attempt already consumed')
                        if not secrets.compare_digest(params.get('state',''),owner.pending['state']): raise RSIError('Invalid OAuth state')
                        owner.consumed=True
                        try:
                            accounts.accept(owner.pending,params)
                            owner.result={'status':'connected'};code=200;message='Přihlášení dokončeno. Vrať se do NeuroPilotu a načti modely.'
                        except (RSIError,OSError):
                            owner.result={'status':'failed','error':'Přihlášení nebylo dokončeno. Zkus nový pokus a povol využití předplatného.'}
                            message=owner.result['error']
                        finally: owner.done.set()
                except (RSIError,ValueError): pass
                body=message.encode()
                self.send_response(code);self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        class BoundedServer(HTTPServer):
            def get_request(self):
                connection,address=super().get_request();connection.settimeout(3)
                return connection,address
            def handle_error(self,*args): pass  # Callback query/code must never enter logs.
        self.server=BoundedServer(('127.0.0.1',0),Handler);self.server.timeout=.2
        try: self.pending,self.url=accounts.prepare(f'http://127.0.0.1:{self.server.server_port}/auth/callback',client_id)
        except Exception: self.server.server_close();raise
        self.thread=threading.Thread(target=self._serve,name='openai-login',daemon=True);self.thread.start()

    def _serve(self):
        try:
            while not self.done.is_set() and time.monotonic()<self.pending['expires']: self.server.handle_request()
            if not self.done.is_set(): self.result={'status':'expired'};self.done.set()
        finally: self.server.server_close()

    def cancel(self):
        with self.guard: self.result={'status':'cancelled'};self.done.set()
        self.thread.join(timeout=1)

_logins={}
_guard=threading.Lock()

def begin_login(accounts,client_id=None):
    key=str(accounts.root.resolve())
    with _guard:
        old=_logins.get(key)
        if old and not old.done.is_set(): raise RSIError('Přihlášení již čeká na dokončení.')
        current=Login(accounts,client_id);_logins[key]=current
        return current

def login_status(accounts):
    with _guard:
        current=_logins.get(str(accounts.root.resolve()))
        return dict(current.result) if current else {'status':'idle'}

def cancel_login(accounts):
    with _guard:
        current=_logins.get(str(accounts.root.resolve()))
        if current: current.cancel()
