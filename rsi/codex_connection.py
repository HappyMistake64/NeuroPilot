"""Bounded Codex app-server connection check and phone-compatible sign-in.

This is deliberately NOT an RSI experiment provider: a Codex turn is not a
measurable single model call. No credentials are read or copied by NeuroPilot.
Protocol: https://developers.openai.com/codex/app-server
"""
import json
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

from .common import RSIError, Unavailable


class AppServer:
    def __init__(self, timeout=120, check=None):
        self.timeout=timeout
        self.deadline=time.monotonic()+timeout
        self.check=check or (lambda: None)
        self.sequence=0
        self.buffer=b''
        self.total=0
        self.events=[]
        self.process=None
        self.selector=selectors.DefaultSelector()
        self.workspace=None

    def __enter__(self):
        binary=shutil.which('codex')
        if not binary:
            self.selector.close()
            raise Unavailable('Codex CLI není nainstalován.')
        self.workspace=tempfile.TemporaryDirectory(prefix='neuropilot-codex-check-')
        # Keep runtime auth, proxy and CA environment unchanged. Disable model
        # tools and hooks explicitly; never use the repository as Codex cwd.
        disabled=('shell_tool','unified_exec','apply_patch_freeform','code_mode',
                  'code_mode_host','js_repl','multi_agent','collab','apps','plugins',
                  'hooks','codex_hooks','plugin_hooks','memories','memory_tool',
                  'web_search','web_search_request','web_search_cached','browser_use',
                  'computer_use','image_generation','view_image','tool_search')
        cmd=[binary,'app-server','--listen','stdio://']
        for feature in disabled: cmd+=['--disable',feature]
        cmd+=['-c','web_search="disabled"']
        try:
            self.process=subprocess.Popen(cmd,cwd=self.workspace.name,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            self.selector.register(self.process.stdout,selectors.EVENT_READ)
            self.rpc('initialize',{'clientInfo':{'name':'NeuroPilot','title':'NeuroPilot','version':'3.4.0'},
                                   'capabilities':{'experimentalApi':True}})
            self.send({'method':'initialized'})
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

    def __exit__(self,*args):
        self.selector.close()
        if self.process:
            try: os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try: os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                self.process.wait(timeout=2)
            for stream in (self.process.stdin,self.process.stdout):
                if stream: stream.close()
        if self.workspace: self.workspace.cleanup()

    def send(self,message):
        try:
            self.process.stdin.write((json.dumps(message)+'\n').encode())
            self.process.stdin.flush()
        except (BrokenPipeError,OSError): raise Unavailable('Codex app-server transport closed') from None

    def receive(self):
        self.check()
        if time.monotonic()>=self.deadline: raise Unavailable('Codex app-server timed out')
        while b'\n' not in self.buffer:
            self.check()
            if time.monotonic()>=self.deadline: raise Unavailable('Codex app-server timed out')
            if not self.selector.select(.1): continue
            data=os.read(self.process.stdout.fileno(),65536)
            if not data: raise Unavailable('Codex app-server exited before completion')
            self.total+=len(data);self.buffer+=data
            if self.total>8_000_000 or len(self.buffer)>2_000_000:
                raise RSIError('Codex app-server response too large')
        line,self.buffer=self.buffer.split(b'\n',1)
        try: message=json.loads(line)
        except (ValueError,UnicodeError): raise RSIError('Invalid Codex app-server JSON') from None
        if not isinstance(message,dict): raise RSIError('Invalid Codex app-server message')
        # No callback supplied by the model may execute a tool or gain permissions.
        if 'method' in message and 'id' in message:
            self.send({'id':message['id'],'error':{'code':-32601,'message':'NeuroPilot does not execute Codex tools'}})
            raise RSIError('Codex requested an unsupported client action')
        return message

    def rpc(self,method,params):
        self.sequence+=1;request_id=self.sequence
        self.send({'id':request_id,'method':method,'params':params})
        while True:
            message=self.receive()
            if message.get('id')==request_id:
                if 'error' in message:
                    # Never echo arbitrary provider messages or config values.
                    raise Unavailable('Codex RPC failed: '+method)
                result=message.get('result')
                if not isinstance(result,dict): raise RSIError('Invalid Codex RPC result')
                return result
            self.events.append(message)
            if len(self.events)>2000: raise RSIError('Too many Codex events')

    def account(self):
        result=self.rpc('account/read',{'refreshToken':False})
        account=result.get('account') or {}
        if not isinstance(account,dict): raise RSIError('Invalid Codex account response')
        return {'auth_type':account.get('type'),'plan_type':account.get('planType'),
                'signed_in':account.get('type')=='chatgpt','model_inference_verified':False}

    def models(self):
        result=self.rpc('model/list',{'limit':100,'includeHidden':False})
        rows=result.get('data')
        if not isinstance(rows,list): raise RSIError('Invalid Codex model catalog')
        return [{'id':r['model'],'default':r.get('isDefault') is True} for r in rows
                if isinstance(r,dict) and isinstance(r.get('model'),str) and not r.get('hidden')]


def status():
    with AppServer(timeout=30) as client:
        result=client.account()
        if result['signed_in']: result['models']=client.models()
        return result


def login():
    """Use the official CLI device flow verified in this cloud environment.

    The CLI shows the temporary code directly; it never enters the RSI audit.
    """
    binary=shutil.which('codex')
    if not binary: raise Unavailable('Codex CLI není nainstalován.')
    with tempfile.TemporaryDirectory(prefix='neuropilot-codex-login-') as cwd:
        process=subprocess.Popen([binary,'login','--device-auth'],cwd=cwd,
                                 stdin=subprocess.DEVNULL,start_new_session=True)
        try:
            deadline=time.monotonic()+600
            while process.poll() is None:
                if time.monotonic()>=deadline: raise Unavailable('Codex device login timed out')
                time.sleep(.2)
            if process.returncode!=0: raise Unavailable('Codex device login failed')
        finally:
            try: os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=2)
    with AppServer(timeout=30) as client:
        account=client.account()
        if not account['signed_in']: raise Unavailable('Codex did not activate a ChatGPT account')
        return account


def connection_check(engine,model=None):
    """One fixed, text-only Codex turn. Never launches RSI candidate code."""
    import secrets
    from .common import BudgetExceeded, Cancelled
    cfg=dict(engine.cfg,max_calls=1)
    with engine.registry.exclusive():
        rid=engine.registry.new_run('codex_connection_check',cfg)
        report={'run_id':rid,'kind':'codex_connection_check','transport':'codex_app_server',
                'model_inference_verified':False,'rsi_experiments_supported':False,
                'actual_rsi_improvement_proven':False,'turns_submitted':0,
                'underlying_model_calls':None,'budget_unit':'codex_turn',
                'token_cap_enforced_by_server':False}
        call=None;usage=None
        try:
            with AppServer(timeout=min(cfg['model_timeout'],cfg['max_seconds']),
                           check=lambda:engine.registry.check(rid)) as client:
                account=client.account()
                if not account['signed_in']:
                    raise Unavailable('Spusť python -m rsi codex-login a dokonči přihlášení z telefonu.')
                report['auth_type']=account['auth_type']
                models=client.models()
                selected=model or next((m['id'] for m in models if m['default']),None)
                if selected not in {m['id'] for m in models}: raise Unavailable('Vyber model z codex-status.')
                # Disable configured MCP servers without printing their config or
                # credentials. Empty environments prevent filesystem tool access.
                settings=client.rpc('config/read',{'includeLayers':False,'cwd':client.workspace.name}).get('config',{})
                servers=settings.get('mcp_servers') or {}
                if not isinstance(servers,dict): raise RSIError('Invalid Codex MCP configuration')
                overrides={'mcp_servers.'+json.dumps(name)+'.enabled':False for name in servers}
                thread=client.rpc('thread/start',{'model':selected,'ephemeral':True,
                    'cwd':client.workspace.name,'sandbox':'read-only','approvalPolicy':'never',
                    'environments':[],'dynamicTools':[],'selectedCapabilityRoots':[],
                    'config':overrides,'serviceName':'NeuroPilot',
                    'baseInstructions':'Return only the requested JSON. Do not use tools.',
                    'developerInstructions':'This is a single connection check. No files, shell, tools or other agents.',
                    'allowProviderModelFallback':False})
                if thread.get('model')!=selected or thread.get('modelProvider')!='openai':
                    raise RSIError('Codex changed the selected model or OpenAI provider')
                if thread.get('sandbox',{}).get('type')!='readOnly':
                    raise RSIError('Codex did not apply read-only sandbox')
                if thread.get('instructionSources'): raise RSIError('Unexpected Codex instruction files')
                thread_id=thread['thread']['id']
                report['model']=selected
                nonce=secrets.token_hex(16)
                expected={'connection':'ok','nonce':nonce}
                prompt='Return exactly this JSON object: '+json.dumps(expected)
                call=engine.registry.reserve(rid,cfg['context_tokens']+cfg['output_tokens'])
                engine.registry.event(rid,'codex_connection_request',{'model':selected,'prompt':prompt,'budget_unit':'codex_turn'})
                report['turns_submitted']=1
                started=client.rpc('turn/start',{'threadId':thread_id,
                    'input':[{'type':'text','text':prompt}],
                    'environments':[],
                    'sandboxPolicy':{'type':'readOnly','networkAccess':False},
                    'outputSchema':{'type':'object','properties':{
                        'connection':{'type':'string','enum':['ok']},'nonce':{'type':'string','enum':[nonce]}},
                        'required':['connection','nonce'],'additionalProperties':False}})
                turn_id=started['turn']['id']
                messages=[];usage=None
                while True:
                    event=client.events.pop(0) if client.events else client.receive()
                    method=event.get('method');params=event.get('params') or {}
                    if params.get('threadId')!=thread_id: continue
                    if method=='thread/tokenUsage/updated':
                        usage=(params.get('tokenUsage') or {}).get('last')
                    if method in ('item/started','item/completed'):
                        item=params.get('item') or {}
                        if item.get('type') not in ('userMessage','agentMessage','reasoning'):
                            raise RSIError('Codex emitted a tool or unexpected output; connection check stopped')
                        if method=='item/completed' and item.get('type')=='agentMessage':
                            messages.append(item.get('text',''))
                    if method=='turn/completed' and params.get('turn',{}).get('id')==turn_id:
                        if params['turn'].get('status')!='completed':
                            detail=params['turn'].get('error') or {}
                            code=detail.get('codexErrorInfo')
                            if code=='unauthorized':
                                report['error_code']='unauthorized'
                                raise Unavailable('Přihlášení Codexu vypršelo nebo bylo odvoláno. Spusť python -m rsi codex-login.')
                            raise Unavailable('Codex turn did not complete')
                        break
                counts=[(usage or {}).get('inputTokens'),(usage or {}).get('outputTokens')]
                actual=sum(counts) if all(type(v) is int and v>=0 for v in counts) else None
                engine.registry.settle(call,actual,{'budget_unit':'codex_turn',
                    'input_tokens':counts[0],'output_tokens':counts[1]})
                content=''.join(messages)
                try: response=json.loads(content)
                except (ValueError,TypeError): raise RSIError('Codex returned invalid connection JSON') from None
                if response!=expected: raise RSIError('Codex connection challenge mismatch')
                engine.registry.event(rid,'codex_connection_response',{'model':selected,'response':response,'actual_tokens':actual})
                engine.registry.check(rid)
                if engine.registry.usage(rid)['charged']>cfg['max_tokens']:
                    raise BudgetExceeded('Codex turn exceeded token accounting budget')
                report['response']=response;report['model_inference_verified']=True
                result_status='complete'
        except (Cancelled,KeyboardInterrupt): result_status='stopped';report['error']='Codex connection check stopped'
        except BudgetExceeded as error: result_status='budget_exhausted';report['error']=str(error)
        except Unavailable as error: result_status='blocked';report['error']=str(error)
        except (RSIError,OSError,KeyError,TypeError,ValueError,AttributeError) as error:
            result_status='failed'
            report['error']=str(error) if isinstance(error,RSIError) else 'Codex connection protocol or process error'
        finally:
            if call:
                with engine.registry.connect() as conn: row=conn.execute('SELECT status FROM calls WHERE id=?',(call,)).fetchone()
                if row and row[0]=='reserved':
                    values=[(usage or {}).get('inputTokens'),(usage or {}).get('outputTokens')]
                    actual=sum(values) if all(type(v) is int and v>=0 for v in values) else None
                    engine.registry.settle(call,actual,{'budget_unit':'codex_turn'},'failed')
        report['status']=result_status;report['usage']=engine.registry.usage(rid)
        engine.registry.finish(rid,result_status,report)
        return report
