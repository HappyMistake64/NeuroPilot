"""Loopback-only accounting gateway for the official Codex custom-provider API.

Codex owns OAuth. The gateway forwards in-memory auth headers to its published
ChatGPT backend, through the inherited cloud proxy. No credential files or logs.
Each forwarded Responses POST reserves a real registry call, including retries.
"""
import io
import json
import multiprocessing
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .common import RSIError, Unavailable, BudgetExceeded, canonical
from .openai_auth import opener, safe_code
from .openai_provider import completed_response

# Default ChatGPT backend published by the official Codex client:
# github.com/openai/codex/blob/main/codex-rs/model-provider-info/src/lib.rs
UPSTREAM='https://chatgpt.com/backend-api/codex/responses'


def parse_stream(raw):
    """Codex may omit accumulated output from its terminal completion event."""
    response=completed_response(io.BytesIO(raw))
    items={};parts=[]
    for line in raw.splitlines():
        if line.startswith(b'data:'):parts.append(line[5:].lstrip())
        elif not line and parts:
            data=b'\n'.join(parts);parts=[]
            if data==b'[DONE]':break
            event=json.loads(data)
            if event.get('type') in ('response.output_item.added','response.output_item.done'):
                item=event.get('item')
                if not isinstance(item,dict) or item.get('type') not in ('reasoning','message'):
                    raise RSIError('Unexpected Codex tool output')
            if event.get('type')=='response.output_item.done':
                index=event.get('output_index');item=event.get('item')
                if type(index) is not int or index<0 or index in items or not isinstance(item,dict):
                    raise RSIError('Invalid Codex output item')
                items[index]=item
            if event.get('type')=='response.completed':break
    if response.get('output'):return response
    if not items:raise RSIError('Codex completion has no output items')
    return dict(response,output=[items[index] for index in sorted(items)])


def exchange(body,headers,timeout,connection):
    """One HTTPS request, no redirect/retry, killable by the trusted broker."""
    try:
        request=Request(UPSTREAM,data=canonical(body).encode(),headers=headers)
        with opener().open(request,timeout=timeout) as response:
            content_type=response.headers.get('Content-Type','')
            if content_type and 'text/event-stream' not in content_type:raise RSIError('Expected SSE')
            raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise RSIError('Response too large')
            completed=parse_stream(raw)
            # Codex never gets an opportunity to execute an unexpected tool.
            output=completed.get('output')
            if not isinstance(output,list): raise RSIError('Missing output')
            if any(not isinstance(item,dict) or item.get('type') not in ('reasoning','message') for item in output):
                raise RSIError('Unexpected tool output')
            connection.send({'ok':True,'raw':raw,'response':completed})
    except HTTPError as error:
        code=None;parameter=None
        try:
            payload=json.loads(error.read(4096));detail=payload.get('error',payload.get('detail',{}))
            code=detail.get('code') if isinstance(detail,dict) else detail
            message=detail.get('message','') if isinstance(detail,dict) else str(detail)
            match=re.search(r"(?:Unsupported parameter|Unknown parameter|Missing required parameter): ['\"]([a-z_]+)",message)
            if match:parameter=match.group(1)
            if message.lower() in ('instructions are required','instructions is required'):parameter='instructions'
        except (ValueError,AttributeError): pass
        connection.send({'ok':False,'status':error.code,'code':safe_code(code),'parameter':parameter})
    except (RSIError,URLError,OSError,ValueError):
        connection.send({'ok':False,'status':502,'code':'upstream_failed'})
    finally: connection.close()


class Gateway:
    def __init__(self,cfg,registry,rid,model,account):
        self.cfg=cfg;self.registry=registry;self.rid=rid;self.model=model;self.account=account
        self.secret=secrets.token_urlsafe(32)
        self.guard=threading.Lock();self.closed=threading.Event()
        self.failure=None;self.responses=[];self.forwarded=0

    def __enter__(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): self.send_error(405)
            def do_POST(self):
                try:
                    if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}' or self.path!=f'/{owner.secret}/responses':
                        self.send_error(404);return
                    if self.headers.get('Origin') or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Encoding'):
                        self.send_error(400);return
                    length=int(self.headers.get('Content-Length','0'))
                    if not 1<=length<=1_000_000: self.send_error(413);return
                    body=json.loads(self.rfile.read(length))
                    token=self.headers.get('Authorization','')
                    account=self.headers.get('ChatGPT-Account-Id')
                    if not token.startswith('Bearer ') or account!=owner.account: self.send_error(403);return
                    # Only the Codex Responses endpoint is available, never an open proxy.
                    result=owner.forward(body,dict(self.headers))
                    raw=result.get('raw')
                    if raw is not None:
                        self.send_response(200);self.send_header('Content-Type','text/event-stream')
                    else:
                        raw=canonical({'error':{'code':result.get('code','request_failed'),'message':'NeuroPilot model gateway rejected the request'}}).encode()
                        self.send_response(result.get('status',502));self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers()
                    self.wfile.write(raw)
                except (ValueError,TypeError,RSIError,OSError):
                    try: self.send_error(400)
                    except OSError: pass
        class Server(ThreadingHTTPServer):
            daemon_threads=True
            def get_request(self):
                conn,addr=super().get_request();conn.settimeout(min(owner.cfg['model_timeout']+5,125));return conn,addr
            def handle_error(self,*args): pass
        self.server=Server(('127.0.0.1',0),Handler)
        self.url=f'http://127.0.0.1:{self.server.server_port}/{self.secret}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        return self

    def __exit__(self,*args):
        self.closed.set();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        # Wait for the active handler to stop its upstream child before returning.
        with self.guard: pass

    def check(self):
        if self.closed.is_set(): raise Unavailable('Codex gateway closed')
        self.registry.check(self.rid)
        if self.failure: raise self.failure

    def forward(self,body,headers):
        with self.guard:
            call=None
            try:
                self.check()
                if not isinstance(body,dict) or body.get('model')!=self.model or body.get('stream') is not True or body.get('store') is not False:
                    raise RSIError('Invalid Codex model request')
                # Inference produces JSON data only. No model-side tools, including
                # any inadvertently inherited from an updated Codex configuration.
                body=dict(body,tools=[])
                body.setdefault('instructions','Return only the JSON requested by NeuroPilot. Never call tools.')
                body.pop('tool_choice',None);body['parallel_tool_calls']=False
                for key in ('previous_response_id','conversation','background'):
                    if body.get(key): raise RSIError('Stateful Codex request rejected')
                if not isinstance(body.get('input'),list): raise RSIError('Invalid Codex input')
                body['input']=[item for item in body['input'] if not (isinstance(item,dict) and item.get('type')=='additional_tools')]
                forbidden=('function_call','function_call_output','custom_tool_call','custom_tool_call_output')
                if any(not isinstance(item,dict) or item.get('type') in forbidden for item in body['input']):
                    raise RSIError('Codex tool input rejected')
                call=self.registry.reserve(self.rid,self.cfg['context_tokens']+self.cfg['output_tokens'])
                self.forwarded+=1
                self.registry.event(self.rid,'model_request',{'call':call,'model':self.model,'transport':'codex_gateway',
                    'seed_applied':False,'request_index':self.forwarded})
                # Forward only headers belonging to the official model request.
                blocked={'host','connection','content-length','transfer-encoding','content-encoding','cookie','proxy-authorization','x-openai-internal-codex-responses-lite'}
                outgoing={k:v for k,v in headers.items() if k.lower() not in blocked}
                outgoing.update({'Content-Type':'application/json','Accept':'text/event-stream'})
                result=self._exchange(body,outgoing)
                if not result['ok']:
                    self.registry.settle(call,None,{'transport':'codex_gateway','http_status':result['status'],'parameter':result.get('parameter')},'failed')
                    return result
                response=result['response'];usage=response.get('usage') or {}
                values=[usage.get('input_tokens'),usage.get('output_tokens')]
                actual=sum(values) if all(type(v) is int and v>=0 for v in values) else None
                self.registry.settle(call,actual,{'transport':'codex_gateway','input_tokens':values[0],'output_tokens':values[1],
                    'reported_model':response.get('model'),'token_cap_enforced_by_server':False})
                self.responses.append(response)
                self.registry.event(self.rid,'model_response',{'call':call,'output':[item for item in response['output'] if item.get('type')=='message'],'actual_tokens':actual,'reported_model':response.get('model')})
                self.registry.check(self.rid)
                if self.registry.usage(self.rid)['charged']>self.cfg['max_tokens']:
                    raise BudgetExceeded('Codex response exceeded token accounting budget')
                return result
            except (RSIError,OSError) as error:
                self.failure=error if isinstance(error,RSIError) else Unavailable('Codex gateway transport failed')
                if call:
                    with self.registry.connect() as conn: row=conn.execute('SELECT status FROM calls WHERE id=?',(call,)).fetchone()
                    if row and row[0]=='reserved':self.registry.settle(call,None,{'transport':'codex_gateway'},'failed')
                return {'ok':False,'status':429 if isinstance(error,BudgetExceeded) else 502,'code':'gateway_stopped'}

    def _exchange(self,body,headers):
        timeout=min(self.cfg['model_timeout'],self.registry.remaining(self.rid))
        context=multiprocessing.get_context('spawn');parent,child=context.Pipe(duplex=False)
        process=context.Process(target=exchange,args=(body,headers,timeout,child))
        deadline=time.monotonic()+timeout
        process.start();child.close()
        try:
            while not parent.poll(.1):
                self.check()
                if time.monotonic()>=deadline: raise Unavailable('Codex gateway timed out')
                if not process.is_alive(): raise Unavailable('Codex gateway worker exited')
            try:return parent.recv()
            except EOFError:raise Unavailable('Codex gateway worker closed') from None
        finally:
            parent.close()
            if process.is_alive():process.terminate()
            process.join(timeout=2)
            if process.is_alive():process.kill();process.join(timeout=2)
