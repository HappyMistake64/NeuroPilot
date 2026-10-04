
from __future__ import annotations
from typing import Dict, Any
import re, random
def goal_gen_module(state: Dict[str,Any]) -> Dict[str,Any]:
    prompt=str(state.get("prompt",""))
    values = state.get("values") or {}
    tasks = list(state.get("tasks", []))
    # novelty trigger: if prompt contains "zkoumej" or "nové", propose a goal
    low = prompt.lower()
    if any(k in low for k in ("zkoumej","nové","novy","novinka")):
        topic = re.sub(r"\s+", " ", prompt)[:50]
        goal = f"Najít 2 příklady pro: {topic}"
        if goal not in tasks:
            tasks.append(goal)
            return {"tasks": tasks, "goal_line": f"Přidán cíl: {goal}"}
    # random small goal when coherence high
    if values.get("coherence",0.6)>0.6 and random.random()<0.15:
        g="Zapsat stručné shrnutí dnešní konverzace"
        if g not in tasks:
            tasks.append(g)
            return {"tasks": tasks, "goal_line": f"Přidán cíl: {g}"}
    return {}
