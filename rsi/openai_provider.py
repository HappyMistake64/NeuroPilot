"""Text-only Responses SSE provider using official ChatGPT plan OAuth.

No API keys, Codex credentials, browser cookies, host tools, or backend-api routes.
Output-token caps and deterministic seeds are unsupported on this preview route;
the registry is an accounting guard, not a server-enforced token spending cap.
"""
import json
import multiprocessing
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request
from .common import RSIError, Unavailable, BudgetExceeded, canonical
from .openai_auth import Accounts, RESOURCE, ServiceError, opener, request_json, safe_code

def completed_response(lines):
    """Bound memory; never accept partial text as a completed model response."""
    total=0;parts=[]
    for line in lines:
        total+=len(line)
        if total>2_000_000 or len(line)>1_000_000: raise RSIError('OpenAI stream too large')
        text=line.decode('utf-8').rstrip('\r\n')
        if text.startswith('data:'): parts.append(text[5:].lstrip(' '))
        elif not text and parts:
            raw='\n'.join(parts);parts=[]
            if raw=='[DONE]': break
            event=json.loads(raw)
            if not isinstance(event,dict): raise RSIError('Invalid OpenAI stream event')
            kind=event.get('type')
            if kind=='response.completed':
                response=event.get('response')
                if not isinstance(response,dict) or response.get('status')!='completed': raise RSIError('Invalid completion event')
                return response
            if kind in ('response.failed','response.incomplete','error'):
                detail=event.get('response',{}).get('error') or event.get('error') or event
                raise ServiceError(safe_code(detail.get('code') if isinstance(detail,dict) else None))
    raise Unavailable('OpenAI stream ended without response.completed')

def _response_exchange(token,body,timeout,connection):
    try:
        req=Request(RESOURCE+'/responses',data=canonical(body).encode(),headers={
            'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'text/event-stream'})
        with opener().open(req,timeout=timeout) as response:
            if 'text/event-stream' not in response.headers.get('Content-Type',''): raise RSIError('Expected OpenAI SSE stream')
            def lines():
                while True:
                    line=response.readline(1_000_001)
                    if not line: break
                    yield line
            connection.send({'ok':True,'response':completed_response(lines())})
    except HTTPError as error:
        code=None
        try:
            body=json.loads(error.read(4096));detail=body.get('error',{})
            code=detail.get('code') if isinstance(detail,dict) else detail
        except (ValueError,AttributeError): pass
        connection.send({'ok':False,'error':safe_code(code),'status':error.code})
    except ServiceError as error:
        connection.send({'ok':False,'error':error.code,'status':error.status})
    except (URLError,OSError,ValueError,RSIError):
        # Neither raw provider errors nor credentials are sent to the audit log.
        connection.send({'ok':False,'error':'stream_failed'})
    finally: connection.close()

class ChatGPT:
    def __init__(self,cfg,registry,accounts=None):
        self.cfg=cfg;self.registry=registry;self.accounts=accounts or Accounts();self.identity=None

    def models(self):
        token,_=self.accounts.credentials()
        response=request_json(RESOURCE+'/models',token=token)
        rows=response.get('models')
        if not isinstance(rows,list): raise Unavailable('OpenAI returned an invalid model catalog')
        return [{'id':m['slug'],'name':m.get('display_name') or m['slug']} for m in rows
                if isinstance(m,dict) and m.get('visibility')=='list' and isinstance(m.get('slug'),str) and m['slug']]

    def probe(self):
        _,account=self.accounts.credentials()
        model=self.cfg['openai_model'].strip()
        if not model: raise Unavailable('Vyber model ChatGPT v nastavení RSI.')
        identity={'provider':'chatgpt_plan','model':model,'account':account,'endpoint':RESOURCE,
                  'seed_supported':False,'weights_pinned':False,'tools':[],
                  'token_budget':'accounting_guard_not_server_cap'}
        if self.identity and identity!=self.identity: raise RSIError('ChatGPT account or model changed during experiment')
        if self.identity is None and model not in {m['id'] for m in self.models()}: raise Unavailable('Vybraný model není v katalogu tohoto účtu. Načti modely znovu.')
        self.identity=identity;return identity

    def _chat(self,body,rid):
        token,account=self.accounts.credentials()
        if account!=self.identity['account']: raise RSIError('ChatGPT account changed during experiment')
        timeout=min(self.cfg['model_timeout'],self.registry.remaining(rid))
        context=multiprocessing.get_context('spawn');parent,child=context.Pipe(duplex=False)
        process=context.Process(target=_response_exchange,args=(token,body,timeout,child))
        deadline=time.monotonic()+timeout
        process.start();child.close()
        try:
            while not parent.poll(.1):
                self.registry.check(rid)
                if time.monotonic()>=deadline: raise Unavailable('OpenAI request timed out')
                if not process.is_alive(): raise Unavailable('OpenAI transport exited')
            try: result=parent.recv()
            except EOFError: raise Unavailable('OpenAI transport closed') from None
            if not result['ok']: raise ServiceError(result['error'],result.get('status'))
            return result['response']
        finally:
            parent.close()
            if process.is_alive(): process.terminate()
            process.join(timeout=2)
            if process.is_alive(): process.kill();process.join()

    def complete(self,messages,rid,seed=0):
        self.registry.check(rid);self.probe()
        if not isinstance(messages,list) or not 1<=len(messages)<=30: raise RSIError('Invalid messages')
        for m in messages:
            if not isinstance(m,dict) or m.get('role') not in ('system','user','assistant') or not isinstance(m.get('content'),str): raise RSIError('Invalid message')
        if sum(len(m['content']) for m in messages)>60000: raise RSIError('Prompt exceeds character limit')
        body={'model':self.identity['model'],'store':False,'stream':True,'tools':[],
              'input':[{'role':'developer' if m['role']=='system' else m['role'],'content':m['content']} for m in messages]}
        cid=self.registry.reserve(rid,self.cfg['context_tokens']+self.cfg['output_tokens'])
        self.registry.event(rid,'model_request',{'call':cid,'model':self.identity,'seed_requested':seed,'seed_applied':False,'messages':messages})
        start=time.monotonic()
        try:
            response=self._chat(body,rid)
            usage=response.get('usage') or {};values=[usage.get('input_tokens'),usage.get('output_tokens')]
            actual=sum(values) if all(type(v) is int and v>=0 for v in values) else None
            self.registry.settle(cid,actual,{'elapsed':time.monotonic()-start,'model':self.identity,
                'reported_model':response.get('model'),'input_tokens':values[0],'output_tokens':values[1],
                'token_cap_enforced_by_server':False})
            if response.get('status')!='completed': raise RSIError('OpenAI response incomplete')
            output=response.get('output')
            if not isinstance(output,list): raise RSIError('Invalid OpenAI output')
            texts=[]
            for item in output:
                if not isinstance(item,dict): raise RSIError('Invalid OpenAI output item')
                if item.get('type')=='reasoning': continue
                if item.get('type')!='message' or item.get('role')!='assistant': raise RSIError('OpenAI returned an unexpected tool or output item')
                for part in item.get('content',[]):
                    if not isinstance(part,dict) or part.get('type')!='output_text' or not isinstance(part.get('text'),str): raise RSIError('OpenAI did not return text')
                    texts.append(part['text'])
            content=''.join(texts)
            self.registry.event(rid,'model_response',{'call':cid,'content':content,'actual_tokens':actual,'reported_model':response.get('model')})
            run=self.registry.check(rid)
            if self.registry.usage(rid)['charged']>run['config']['max_tokens']:
                raise BudgetExceeded('ChatGPT response exceeded the token accounting budget; stopped before another call')
            try: result=json.loads(content)
            except ValueError: raise RSIError('OpenAI must return a JSON object') from None
            if not isinstance(result,dict): raise RSIError('OpenAI must return a JSON object')
            return result
        except Exception as error:
            with self.registry.connect() as conn: row=conn.execute('SELECT status FROM calls WHERE id=?',(cid,)).fetchone()
            if row and row[0]=='reserved': self.registry.settle(cid,None,{'error':type(error).__name__},'failed')
            raise
