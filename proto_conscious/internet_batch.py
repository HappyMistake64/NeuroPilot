
from __future__ import annotations
from typing import Dict, Any
import os, time, urllib.parse, urllib.request, html, re, json
STATE="internet_state.json"
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
def _q2u(q:str)->str:
    q=q.strip()
    if q.startswith("http"): return q
    from urllib.parse import urlencode
    return "https://arxiv.org/search/?"+ urlencode({"query": q, "searchtype":"all"})
def internet_batch_module(state: Dict[str,Any]) -> Dict[str,Any]:
    cfg=state.get("web_cfg") or {}
    if not (cfg.get("enabled", False) and cfg.get("batch_enabled", True)): return {}
    raw=str(state.get("prompt","")); low=raw.lower()
    if not (low.startswith("hledej:") or low.startswith("search:")): return {}
    parts=[p.strip() for p in raw.split(":",1)[-1].split(",") if p.strip()]
    if len(parts)<=1: return {}
    base=state.get("basepath"); st=_load(_spath(base))
    per=int(cfg.get("rate_limit_per_min",6)); timeout=int(cfg.get("timeout_seconds",5))
    maxb=int(cfg.get("max_bytes",800000)); wl=cfg.get("whitelist",[])
    maxc=1100 if cfg.get("extended_summary",False) else 700
    limit=int(cfg.get("batch_max",3))
    results=[]; done=0
    for q in parts:
        if done>=limit: break
        if not _rate(st, per): results.append("• rate-limit: dokončím později"); break
        url=_q2u(q)
        if not _allowed(url, wl): results.append(f"• {q} → blokováno (mimo whitelist)"); continue
        try:
            c,d=_fetch(url, timeout, maxb, wl); text=_text(d)
            # simple short summary
            sents=re.split(r"(?<=[.!?])\s+", text); out=""
            for s in sents:
                if len(out)+len(s)>maxc: break
                out+=s.strip()+" "
            results.append(f"• {q} → {out.strip()} [zdroj: {url}]")
        except Exception as e:
            results.append(f"• {q} → chyba: {e}")
        done+=1
    _save(_spath(base), st)
    if not results: return {}
    base_reply=state.get("candidate_reply","")
    block="🔎 Výsledky hledání:\n" + "\n".join(results)
    if base_reply: base_reply+=" "
    return {"candidate_reply": base_reply+block}
