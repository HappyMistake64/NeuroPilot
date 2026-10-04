
from __future__ import annotations
from typing import Dict, Any
import re
def _score(prompt:str, text:str)->float:
    p=set(re.findall(r"[A-Za-zÀ-ž0-9]{3,}", prompt.lower()))
    t=re.findall(r"[A-Za-zÀ-ž0-9]{3,}", text.lower())
    if not t: return 0.0
    hits=sum(1 for w in t if w in p); base=min(1.0, hits/max(1,len(p))*0.6)
    if "abstract" in text.lower() or "doi" in text.lower(): base+=0.2
    if "introduction" in text.lower() or "method" in text.lower(): base+=0.1
    return max(0.0, min(1.0, base))
def _summ(text:str, max_chars:int)->str:
    s=re.split(r"(?<=[.!?])\s+", text); out=""
    for x in s:
        if len(out)+len(x)>max_chars: break
        out+=x.strip()+" "
    return out.strip()
def relevance_filter_module(state: Dict[str,Any]) -> Dict[str,Any]:
    text = state.get("web_text"); 
    if not text: return {}
    prompt = str(state.get("prompt",""))
    url = state.get("web_url","")
    maxc = 1100 if (state.get("web_cfg") or {}).get("extended_summary", False) else 700
    s=_score(prompt, text)
    if s<0.25: return {"web_note":"low relevance"}
    summary=_summ(text, maxc)
    base=state.get("candidate_reply","")
    if base: base+=" "
    return {"candidate_reply": (base + summary + f" [zdroj: {url}]").strip()}
