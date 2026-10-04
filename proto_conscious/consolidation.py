
from __future__ import annotations
from typing import Dict, Any
import re
def _summarize(texts, max_len=600):
    flat=" ".join(texts)[-4000:]
    s=re.split(r"(?<=[.!?])\s+", flat); out=""
    for sent in s:
        if len(out)+len(sent)>max_len: break
        out+=sent.strip()+" "
    return out.strip()
def consolidation_module(state: Dict[str,Any]) -> Dict[str,Any]:
    prompt=str(state.get("prompt","")).strip().lower()
    if prompt != ":sleep": return {}
    ctx = state.get("context", [])
    cfg = state.get("cons_cfg") or {"summary_len":600, "value_lr":0.03}
    summary=_summarize(ctx, cfg.get("summary_len",600)) if ctx else "(prázdno)"
    values = state.get("values") or {}
    # small homeostatic tweak: reward coherence, reduce novelty a bit
    values["coherence"] = min(1.0, values.get("coherence",0.6) + cfg.get("value_lr",0.03))
    values["novelty"]   = max(0.0, values.get("novelty",0.55) - cfg.get("value_lr",0.03)/2)
    return {"sleep_line": f"Spánek: konsolidace hotová. Shrnutí: {summary[:140]}…", "values": values}
