
from __future__ import annotations
from typing import Dict, Any
import random
def future_sim_module(state: Dict[str,Any]) -> Dict[str,Any]:
    prompt=str(state.get("prompt",""))
    if len(prompt)<3: return {}
    options=[("udělat malý krok hned",0.6),("nejdřív si upřesnit cíl",0.75),("najít protipříklad a pak jednat",0.7)]
    best=max(options, key=lambda x:x[1]+random.random()*0.05)
    return {"critique":f"Sandbox: vede varianta „{best[0]}“."}
