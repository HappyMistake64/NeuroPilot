"""Explicit real providers. No simulated or API-key fallback."""
import json
import time
import multiprocessing
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import URLError
from .common import RSIError, Unavailable, canonical, digest

def make_provider(cfg, registry):
    if cfg['provider']=='codex':
        from .codex_provider import Codex
        return Codex(cfg, registry)
    if cfg['provider']=='chatgpt':
        from .openai_provider import ChatGPT
        return ChatGPT(cfg, registry)
    return Ollama(cfg, registry)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise Unavailable('Provider redirects are not allowed')

def _exchange(base, body, timeout, connection):
    """Trusted transport child; terminating it closes the HTTP request."""
    try:
        opener=build_opener(ProxyHandler({}),NoRedirect())
        req=Request(base+'/api/chat',data=canonical(body).encode(),headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=timeout) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise RSIError('Provider response too large')
            data=json.loads(raw)
            if not isinstance(data,dict) or data.get('error'): raise RSIError('Invalid provider response')
            connection.send({'ok':True,'data':data})
    except Exception as error:
        connection.send({'ok':False,'error':type(error).__name__})
    finally: connection.close()

class Ollama:
    def __init__(self,cfg,registry):
        self.cfg=cfg;self.registry=registry;self.identity=None
        url=urlsplit(cfg['ollama_url'])
        if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:
            raise RSIError('RSI accepts only a local HTTP Ollama endpoint')
        self.base=cfg['ollama_url'].rstrip('/')
        self.opener=build_opener(ProxyHandler({}),NoRedirect())
    def _request(self,path,body=None,timeout=5):
        data=canonical(body).encode() if body is not None else None
        req=Request(self.base+path,data=data,headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=timeout) as response:
                raw=response.read(2_000_001)
                if len(raw)>2_000_000: raise RSIError('Provider response too large')
                result=json.loads(raw)
                if not isinstance(result,dict) or result.get('error'): raise RSIError('Provider error: '+str(result.get('error'))[:200])
                return result
        except (URLError,OSError,ValueError) as error: raise Unavailable('Ollama unavailable or returned invalid JSON') from error
    def probe(self):
        if not self.cfg['model'].strip(): raise Unavailable('Set model in RSI configuration first')
        models=self._request('/api/tags').get('models',[])
        name=self.cfg['model']; names={name,name+':latest'}
        found=next((m for m in models if m.get('name') in names and m.get('digest')),None)
        if not found: raise Unavailable('Configured model is not installed in Ollama')
        identity={'provider':'ollama','model':found['name'],'digest':found['digest'],'endpoint':self.base}
        if self.identity and self.identity!=identity: raise RSIError('Model changed during experiment')
        self.identity=identity;return identity
    def _chat(self,body,rid):
        timeout=min(self.cfg['model_timeout'],self.registry.remaining(rid))
        context=multiprocessing.get_context('spawn')
        parent,child=context.Pipe(duplex=False)
        process=context.Process(target=_exchange,args=(self.base,body,timeout,child))
        deadline=time.monotonic()+timeout
        process.start();child.close()
        try:
            while not parent.poll(.1):
                self.registry.check(rid)
                if time.monotonic()>=deadline: raise Unavailable('Model request timed out')
                if not process.is_alive(): raise Unavailable('Model transport exited')
            result=parent.recv()
            self.registry.check(rid)
            if not result['ok']: raise Unavailable('Model transport failed: '+result['error'])
            return result['data']
        finally:
            parent.close()
            if process.is_alive(): process.terminate()
            process.join(timeout=2)
            if process.is_alive(): process.kill();process.join()

    def complete(self,messages,rid,seed=0):
        self.probe()
        if not isinstance(messages,list) or len(messages)>30: raise RSIError('Invalid messages')
        for m in messages:
            if m.get('role') not in ('system','user','assistant') or not isinstance(m.get('content'),str): raise RSIError('Invalid message')
        if sum(len(m['content']) for m in messages)>60000: raise RSIError('Prompt exceeds character limit')
        reservation=self.cfg['context_tokens']+self.cfg['output_tokens']
        cid=self.registry.reserve(rid,reservation)
        self.registry.event(rid,'model_request',{'call':cid,'model':self.identity,'seed':seed,'messages':messages})
        start=time.monotonic()
        try:
            response=self._chat({'model':self.identity['model'],'messages':messages,'stream':False,'format':'json','options':{'temperature':0,'seed':seed,'num_ctx':self.cfg['context_tokens'],'num_predict':self.cfg['output_tokens']}},rid)
            if response.get('done') is not True: raise RSIError('Model response incomplete')
            content=response.get('message',{}).get('content')
            if not isinstance(content,str): raise RSIError('Missing model output')
            values=[response.get('prompt_eval_count'),response.get('eval_count')]
            actual=sum(values) if all(type(v) is int and v>=0 for v in values) else None
            self.registry.settle(cid,actual,{'elapsed':time.monotonic()-start,'model':self.identity,'input_tokens':values[0],'output_tokens':values[1]})
            self.registry.event(rid,'model_response',{'call':cid,'content':content,'actual_tokens':actual})
            self.registry.check(rid)
            result=json.loads(content)
            if not isinstance(result,dict): raise RSIError('Model must return a JSON object')
            return result
        except Exception as error:
            # Keep a known actual count if parsing failed after a successful response.
            with self.registry.connect() as c: row=c.execute('SELECT status FROM calls WHERE id=?',(cid,)).fetchone()
            if row and row[0]=='reserved': self.registry.settle(cid,None,{'error':type(error).__name__},'failed')
            raise
