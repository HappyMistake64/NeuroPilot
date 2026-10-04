
from __future__ import annotations
from typing import Dict, Any
import os, time, urllib.parse, urllib.request, html, re, json
STATE = "internet_state.json"
def _spath(base): return os.path.join(base, STATE)
def _load(path):
    if not os.path.exists(path): return {"ts":[]}
    try: return json.load(open(path,"r",encoding="utf-8"))
    except: return {"ts":[]}
def _save(path, st):
    from storage import JsonStore
    JsonStore(path, {}).write(st)
def _allowed(url, wl):
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    return parts.scheme in {"http", "https"} and not parts.username and not parts.password and any(host == w.lower().rstrip(".") or host.endswith("." + w.lower().rstrip(".")) for w in wl if w)
def _rate(st, n):
    now=time.time(); st["ts"]=[t for t in st.get("ts",[]) if now-t<60]
    if len(st["ts"])>=n: return False
    st["ts"].append(now); return True
def _fetch(url, timeout, max_bytes, whitelist=None):
    from web_tools import fetch_bytes
    return fetch_bytes(url, timeout, max_bytes, whitelist)
def _text(data):
    from web_tools import clean_text
    return clean_text(data)
def internet_sensor_module(state: Dict[str,Any]) -> Dict[str,Any]:
    cfg = state.get("web_cfg") or {}
    if not cfg.get("enabled", False): return {}
    raw=str(state.get("prompt","")).lower()
    if not (raw.startswith("hledej:") or raw.startswith("search:")): return {}
    q = str(state.get("prompt","")).split(":",1)[-1].strip()
    if "," in q: return {}  # batch handled elsewhere
    base=state.get("basepath"); st=_load(_spath(base))
    if not _rate(st, int(cfg.get("rate_limit_per_min",6))):
        _save(_spath(base), st); return {"web_note":"rate-limit"}
    from urllib.parse import urlencode
    url = "https://arxiv.org/search/?" + urlencode({"query": q, "searchtype":"all"})
    if not _allowed(url, cfg.get("whitelist", [])):
        _save(_spath(base), st); return {"web_note":"blocked by whitelist"}
    try:
        ctype,data=_fetch(url, int(cfg.get("timeout_seconds",5)), int(cfg.get("max_bytes",800000)), cfg.get("whitelist", []))
        text=_text(data)
        _save(_spath(base), st); 
        return {"web_text": text, "web_url": url}
    except Exception as e:
        _save(_spath(base), st); return {"web_note": f"error: {e}"}
