
from __future__ import annotations
from typing import Dict, Any
import math
ALLOWED={"truth","novelty","coherence"}
def self_mod_module(state: Dict[str,Any]) -> Dict[str,Any]:
    text=str(state.get("prompt","")).strip()
    if not text.startswith(":self "): return {}
    parts=text.split()
    if len(parts)<3: return {"reply":"Použití: :self <truth|novelty|coherence> <0..1>"}
    key, val = parts[1], parts[2]
    if key not in ALLOWED: return {"reply":"Tento parametr nemohu měnit."}
    try: v=float(val)
    except: return {"reply":"Hodnota musí být číslo 0..1."}
    if not math.isfinite(v): return {"reply":"Hodnota musí být konečné číslo."}
    v=max(0.0,min(1.0,v))
    values=state.get("values") or {}; values[key]=v
    return {"reply":f"Nastavuji {key} → {v:.2f}","values":values}
