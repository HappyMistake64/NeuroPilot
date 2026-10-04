
from __future__ import annotations
from typing import Dict, Any
def other_self_module(state: Dict[str,Any]) -> Dict[str,Any]:
    prompt=str(state.get("prompt",""))
    os_mem = state.get("other_mem") or {}
    tag = None
    if prompt.startswith("AI-1:"): tag="AI-1"
    if prompt.startswith("AI-2:"): tag="AI-2"
    if not tag: return {}
    text = prompt.split(":",1)[-1].strip()
    hist = os_mem.get(tag, [])
    hist.append(text)
    os_mem[tag] = hist[-16:]
    guess = "má odlišný cíl" if "cí" in text.lower() else "má částečné znalosti"
    return {"other_mem": os_mem, "social_line": f"{tag} → {guess} (zaznamenáno {len(hist)} vět)"}
