
from __future__ import annotations
from typing import Dict, Any, List
def working_memory_module(state: Dict[str,Any]) -> Dict[str,Any]:
    cfg = state.get("wm_cfg") or {"slots":6,"decay":0.9,"boost_focus":0.2}
    wm: List[Dict[str,Any]] = state.get("wm_state") or []
    prompt = str(state.get("prompt",""))
    # decay existing
    for it in wm: it["w"] *= cfg.get("decay",0.9)
    # add new focus item
    wm.append({"t": prompt[:80], "w": 1.0 + cfg.get("boost_focus",0.2)})
    # keep top-k
    wm = sorted(wm, key=lambda x:-x["w"])[:int(cfg.get("slots",6))]
    line = " | ".join(f"{i+1}:{it['t']}({it['w']:.2f})" for i,it in enumerate(wm))
    return {"wm_state": wm, "wm_line": line, "narrative_line": f"Pozornost drží {len(wm)} stop"}
