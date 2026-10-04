"""Fail-closed Linux isolation. Candidate programs are NEVER run on the host."""
import ctypes
import ctypes.util
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from .common import RSIError, Unavailable, Cancelled, relative_file, digest

@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str
    elapsed: float
    timed_out: bool = False
    backend: str = ''
    peak_ram_bytes: object = None
    def as_dict(self): return asdict(self)

PROBE = '''import json, os, socket
checks = {}
for path in ("/work/main.py", "/etc/passwd", "/root", "/workspace"):
    try:
        with open(path, "a") as f: f.write("BAD")
        checks[path] = False
    except OSError: checks[path] = True
try:
    socket.create_connection(("1.1.1.1",443),timeout=.2)
    checks["network"] = False
except OSError: checks["network"] = True
checks["no_keys"] = all(k not in os.environ for k in ("OPENAI_API_KEY","HF_TOKEN"))
print(json.dumps(checks))
'''

class Sandbox:
    def __init__(self,cfg):
        self.cfg=cfg; self.backend=None; self.identity=None; self._probe=None
    def _process(self,cmd,cwd,timeout,cancel=None,pass_fds=(),memory=0):
        env={key:value for key,value in os.environ.items() if key in ('PATH','HOME','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS')}
        env['PATH']=os.defpath
        launcher=Path(__file__).with_name('limits_worker.py')
        command=[sys.executable,'-I',str(launcher),str(memory),str(max(2,math.ceil(timeout))),*cmd]
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            start=time.monotonic(); timed=False
            proc=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,pass_fds=pass_fds)
            try:
                while proc.poll() is None:
                    if cancel: cancel()
                    if time.monotonic()-start>timeout:
                        timed=True; break
                    time.sleep(.025)
            finally:
                if proc.poll() is None:
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                proc.wait()
            out.seek(0);err.seek(0)
            return Result(proc.returncode,out.read(65537).decode('utf-8','replace'),err.read(65537).decode('utf-8','replace'),time.monotonic()-start,timed,self.backend or '')
    def _seccomp(self,fd):
        libname=ctypes.util.find_library('seccomp')
        if not libname: raise Unavailable('libseccomp is required for bwrap')
        lib=ctypes.CDLL(libname)
        lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
        lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
        lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
        lib.seccomp_export_bpf.argtypes=[ctypes.c_void_p,ctypes.c_int]
        lib.seccomp_release.argtypes=[ctypes.c_void_p]
        ctx=lib.seccomp_init(0x7fff0000)
        if not ctx: raise Unavailable('seccomp initialization failed')
        try:
            for name in ('fork','vfork','clone','clone3','socket','socketpair','ptrace','process_vm_readv','process_vm_writev'):
                number=lib.seccomp_syscall_resolve_name(name.encode())
                if number>=0 and lib.seccomp_rule_add(ctx,0x00050000|1,number,0)!=0:
                    raise Unavailable('seccomp rule failed')
            if lib.seccomp_export_bpf(ctx,fd)!=0: raise Unavailable('seccomp export failed')
            os.lseek(fd,0,0)
        finally: lib.seccomp_release(ctx)
    def _execute(self,folder,timeout,cancel):
        exe=shutil.which(self.backend)
        if not exe: raise Unavailable(f'{self.backend} executable missing')
        if self.backend in ('docker','podman'):
            name='neuropilot-'+uuid.uuid4().hex[:12]
            cmd=[exe,'run','--name',name,'--pull=never','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=32',f'--memory={self.cfg["memory_mb"]}m','--cpus=1','--user=65534:65534','--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m','--volume',str(folder)+':/work:ro,Z','--workdir=/work','--env=PYTHONDONTWRITEBYTECODE=1',self.identity,'python','-I','-B','/work/main.py']
            try: return self._process(cmd,folder,timeout,cancel)
            finally:
                subprocess.run([exe,'rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        with tempfile.TemporaryFile() as sec:
            self._seccomp(sec.fileno())
            cmd=[exe,'--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL','--clearenv','--ro-bind','/usr','/usr']
            for item in ('/lib','/lib64'):
                if Path(item).exists(): cmd += ['--ro-bind',item,item]
            cmd += ['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(folder),'/work','--chdir','/work','--setenv','PATH','/usr/bin:/bin','--setenv','PYTHONDONTWRITEBYTECODE','1','--seccomp',str(sec.fileno()),'/usr/bin/python3','-I','-B','/work/main.py']
            return self._process(cmd,folder,timeout,cancel,(sec.fileno(),),self.cfg['memory_mb'])
    def run(self,files,timeout=None,cancel=None,_probing=False):
        if not self.backend: self.probe()
        timeout=min(timeout or self.cfg['sandbox_timeout'],self.cfg['sandbox_timeout'])
        with tempfile.TemporaryDirectory(prefix='neuropilot-sandbox-') as temp:
            root=Path(temp);root.chmod(0o755)
            for name,content in files.items():
                path=relative_file(root,name);path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content,encoding='utf-8');path.chmod(0o644)
            result=self._execute(root,timeout,cancel)
        return result
    def probe(self):
        if self._probe: return self._probe
        requested=self.cfg['sandbox']; failures=[]
        for backend in (['podman','docker','bwrap'] if requested=='auto' else [requested]):
            if not shutil.which(backend): failures.append(backend+': not installed');continue
            self.backend=backend
            try:
                if backend in ('docker','podman'):
                    proc=subprocess.run([shutil.which(backend),'image','inspect',self.cfg['image'],'--format','{{.Id}}'],capture_output=True,text=True,timeout=10)
                    if proc.returncode: raise Unavailable('Local container image unavailable; pull it explicitly first')
                    self.identity=proc.stdout.strip()
                    if not self.identity.startswith('sha256:'): raise Unavailable('Image digest missing')
                else:
                    self.identity='bwrap:'+digest(Path(shutil.which('bwrap')).read_bytes())+':python:'+digest(Path('/usr/bin/python3').resolve().read_bytes())
                with tempfile.NamedTemporaryFile(prefix='neuropilot-host-secret-') as marker:
                    marker.write(b'host-only');marker.flush()
                    source=PROBE.replace('print(json.dumps(checks))', 'try:\n    open('+repr(marker.name)+', \"rb\").read()\n    checks[\"host_secret_hidden\"] = False\nexcept OSError: checks[\"host_secret_hidden\"] = True\nprint(json.dumps(checks))')
                    result=self.run({'main.py':source},_probing=True)
                if result.returncode or result.timed_out: raise Unavailable("Isolation probe failed: "+result.stderr[:200])
                checks=json.loads(result.stdout)
                if result.returncode or result.timed_out or not checks or not all(x is True for x in checks.values()): raise Unavailable('Isolation probe failed')
                self._probe={'backend':backend,'identity':self.identity,'checks':checks,'memory_limit_mb':self.cfg['memory_mb'],'peak_ram_measured':False}
                return self._probe
            except (OSError,subprocess.SubprocessError,ValueError,RSIError) as error:
                failures.append(f'{backend}: {str(error)[:250]}');self.backend=None;self.identity=None
        raise Unavailable('No verified sandbox. '+ '; '.join(failures))
