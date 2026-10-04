
from __future__ import annotations
from typing import Dict, Any
import math
ALLOWED = {
  "working_memory.slots": (2, 12),
  "working_memory.decay": (0.7, 0.99),
  "working_memory.boost_focus": (0.0, 0.5),
  "consolidation.summary_len": (200, 1500),
  "consolidation.value_lr": (0.0, 0.2)
}
def self_rewrite_module(state: Dict[str,Any]) -> Dict[str,Any]:
    text=str(state.get("prompt","")).strip()
    if not text.startswith(":rewrite "): return {}
    parts=text.split()
    if len(parts)<3: return {"reply":"Použití: :rewrite modul.param hodnota"}
    key, val = parts[1], parts[2]
    if key not in ALLOWED: return {"reply":"Tento parametr nelze měnit."}
    lo, hi = ALLOWED[key]
    try:
        v=float(val)
    except:
        return {"reply":"Hodnota musí být číslo."}
    if not math.isfinite(v): return {"reply":"Hodnota musí být konečné číslo."}
    v=max(lo, min(hi, v))
    # Write into config-like mirrors
    cfg = {}
    if key.startswith("working_memory."):
        cfg["wm_cfg"] = dict(state.get("wm_cfg") or {})
        cfg["wm_cfg"][key.split(".",1)[-1]] = v
    elif key.startswith("consolidation."):
        cfg["cons_cfg"] = dict(state.get("cons_cfg") or {})
        cfg["cons_cfg"][key.split(".",1)[-1]] = v
    note=f"Nastavuji {key} → {v}"
    return dict(cfg, reply=note)
