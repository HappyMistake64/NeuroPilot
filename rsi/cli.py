"""python -m rsi; user-selected local state, no background work on import."""
import argparse
import json
import os
from pathlib import Path
from .common import RSIError, DEFAULTS, atomic_json, load_config
from .engine import Engine
from .study import Study, validate_manifest, estimate

def main(argv=None):
    parser=argparse.ArgumentParser(description='NeuroPilot RSI experimental controller')
    parser.add_argument('--state',default=os.environ.get('NEUROPILOT_RSI_STATE',str(Path(__file__).resolve().parents[1]/'rsi_state')))
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('init','doctor','status','reference-check','rollback','recover','provider-check','openai-status','openai-models','openai-logout','codex-status','codex-login'): sub.add_parser(name)
    p=sub.add_parser('codex-check');p.add_argument('--model')
    p=sub.add_parser('openai-login');p.add_argument('--account');p.add_argument('--no-browser',action='store_true')
    p=sub.add_parser('openai-import',help='Import a protected NeuroPilot registration on a remote VM')
    p.add_argument('--file',required=True);p.add_argument('--account',required=True)
    p=sub.add_parser('config');p.add_argument('--set',action='append',default=[])
    p=sub.add_parser('baseline');p.add_argument('--limit',type=int)
    p=sub.add_parser('campaign');p.add_argument('--generations',type=int,default=1)
    p=sub.add_parser('study-create');p.add_argument('file')
    p=sub.add_parser('study-plan');p.add_argument('file')
    p=sub.add_parser('study');p.add_argument('file')
    p=sub.add_parser('activate');p.add_argument('artifact')
    p=sub.add_parser('stop');p.add_argument('run')
    p=sub.add_parser('report');p.add_argument('run');p.add_argument('--output')
    p=sub.add_parser('import-benchmark');p.add_argument('file')
    args=parser.parse_args(argv)
    try:
        if args.command=='config':
            path=Path(args.state)/'config.json';cfg=load_config(args.state)
            for setting in args.set:
                key,sep,value=setting.partition('=')
                if not sep or key not in DEFAULTS: raise RSIError('Use --set known_key=value')
                try: value=json.loads(value)
                except json.JSONDecodeError: pass
                cfg[key]=value
            # Validate in an isolated temporary directory before changing a working config.
            import tempfile
            with tempfile.TemporaryDirectory() as temp:
                atomic_json(Path(temp)/'config.json',cfg);load_config(temp)
            engine=Engine(args.state)
            with engine.registry.exclusive(): atomic_json(path,cfg)
            result=cfg
        else:
            engine=Engine(args.state)
            if args.command=='init': result=engine.init()
            elif args.command=='doctor': result=engine.doctor()
            elif args.command=='provider-check': result=engine.provider_check()
            elif args.command=='codex-check':
                from .codex_connection import connection_check
                result=connection_check(engine,args.model)
            elif args.command=='codex-status':
                from .codex_connection import status
                result=status()
            elif args.command=='codex-login':
                from .codex_connection import login
                try: result=login()
                except KeyboardInterrupt: result={'status':'cancelled','model_inference_verified':False}
            elif args.command.startswith('openai-'):
                from .openai_auth import Accounts, begin_login
                accounts=Accounts()
                if args.command=='openai-status': result=accounts.status()
                elif args.command=='openai-import': result=accounts.import_registration(args.file,args.account,(args.state,))
                elif args.command=='openai-logout': result=accounts.logout()
                elif args.command=='openai-models':
                    from .openai_provider import ChatGPT
                    result={'models':ChatGPT(engine.cfg,engine.registry,accounts).models()}
                else:
                    import webbrowser
                    login=begin_login(accounts,args.account)
                    print('Otevři v prohlížeči na tomto počítači:\n'+login.url,flush=True)
                    if not args.no_browser: webbrowser.open(login.url)
                    try:
                        while not login.done.wait(.2): pass
                    except KeyboardInterrupt: login.cancel()
                    result=dict(login.result)
            elif args.command=='status': result=engine.status()
            elif args.command=='reference-check': result=engine.reference_check()
            elif args.command=='baseline': result=engine.baseline(args.limit)
            elif args.command=='campaign': result=engine.campaign(args.generations)
            elif args.command=='study-create': result=Study(engine).create_manifest(args.file)
            elif args.command=='study-plan':
                data=validate_manifest(json.loads(Path(args.file).read_text()),engine.cfg['min_new_wins']);result=estimate(data,engine.cfg)
            elif args.command=='study': result=Study(engine).run(args.file)
            elif args.command=='activate': result=engine.activate(args.artifact)
            elif args.command=='stop': engine.registry.stop(args.run);result={'stop_requested':args.run}
            elif args.command=='rollback':
                with engine.registry.exclusive(): result={'active':engine.registry.rollback()}
            elif args.command=='recover':
                with engine.registry.exclusive():
                    with engine.registry.connect() as c: ids=[r[0] for r in c.execute("SELECT id FROM runs WHERE status='running'")]
                    for rid in ids:engine.registry.finish(rid,'interrupted',{'run_id':rid,'status':'interrupted','error':'Previous process terminated; no result inferred'})
                result={'interrupted_runs':ids}
            elif args.command=='report':
                result=engine.registry.run(args.run)
                if args.output: atomic_json(Path(args.output),result)
            elif args.command=='import-benchmark':
                with engine.registry.exclusive(): result=engine.benchmark.import_file(args.file)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result.get('status') in ('blocked','failed','budget_exhausted','stopped','expired','cancelled') or result.get('ready') is False: return 2
        return 0
    except (RSIError,OSError,ValueError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False));return 2

if __name__=='__main__': raise SystemExit(main())
