
from __future__ import annotations
from typing import Dict, Any
def feedback_learning_module(state: Dict[str,Any]) -> Dict[str,Any]:
    text=str(state.get("prompt","")).strip().lower()
    values=state.get("values") or {}
    if text.startswith("fb "):
        try: score=int(text.split()[1])
        except: return {"reply":"Feedback musí být -1/0/+1."}
        if score not in (-1, 0, 1): return {"reply":"Feedback musí být -1/0/+1."}
        delta = 0.05 if score>0 else (-0.05 if score<0 else 0.0)
        for k in ("truth","novelty","coherence"):
            if k in values: values[k]=max(0.0,min(1.0, values.get(k,0.6)+delta))
        return {"reply":f"Díky, upravuji preference (Δ={delta:+.2f}).","values":values}
    return {}
