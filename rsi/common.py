"""Shared validation; no candidate code executes in this process."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

class RSIError(Exception): pass
class Unavailable(RSIError): pass
class BudgetExceeded(RSIError): pass
class Cancelled(RSIError): pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()

def atomic_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(canonical(data)); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def relative_file(root, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name:
        raise RSIError('Invalid relative file name')
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts or any(part.startswith('.') for part in rel.parts):
        raise RSIError('Path outside project')
    root = Path(root).resolve(); path = root / rel
    if any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
        raise RSIError('Symlinks are not allowed')
    if not path.resolve().is_relative_to(root): raise RSIError('Path outside project')
    return path

DEFAULTS = {
    'provider': 'ollama', 'openai_model': '',
    'model': '', 'ollama_url': 'http://127.0.0.1:11434',
    'sandbox': 'auto', 'image': 'python:3.12-slim',
    'sandbox_timeout': 10, 'memory_mb': 512,
    'model_timeout': 120, 'context_tokens': 8192, 'output_tokens': 2048,
    'max_calls': 150, 'max_tokens': 1600000, 'max_seconds': 1800,
    'steps_per_task': 3, 'max_generations': 2, 'stagnation_limit': 3,
    'max_files': 3, 'max_changed_lines': 200,
    'auto_promote': False, 'min_new_wins': 2, 'repeats': 3,
    'allow_efficiency': True, 'min_token_saving_percent': 15,
}

def load_config(root):
    path = Path(root) / 'config.json'
    custom = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(custom, dict) or set(custom) - set(DEFAULTS): raise RSIError('Unknown RSI configuration keys')
    cfg = dict(DEFAULTS, **custom)
    for key in ('sandbox_timeout','memory_mb','model_timeout','context_tokens','output_tokens','max_calls','max_tokens','max_seconds','steps_per_task','max_generations','stagnation_limit','max_files','max_changed_lines','min_new_wins','repeats'):
        if type(cfg[key]) is not int or cfg[key] <= 0: raise RSIError(f'{key} must be a positive integer')
    if cfg['sandbox'] not in {'auto','docker','podman','bwrap'}: raise RSIError('Unsupported sandbox')
    if cfg['provider'] not in {'ollama','chatgpt'}: raise RSIError('Unsupported model provider')
    for key in ('auto_promote','allow_efficiency'):
        if type(cfg[key]) is not bool: raise RSIError(f'{key} must be boolean')
    if type(cfg['min_token_saving_percent']) is not int or not 1<=cfg['min_token_saving_percent']<=99:
        raise RSIError('min_token_saving_percent must be an integer from 1 to 99')
    for key in ('model','ollama_url','image','openai_model'):
        if not isinstance(cfg[key],str): raise RSIError(f'{key} must be text')
    return cfg
