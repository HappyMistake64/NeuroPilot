
from __future__ import annotations
from typing import Dict, Any
def metapref_module(state: Dict[str,Any]) -> Dict[str,Any]:
    mp=state.get("metaprefs") or {}
    if mp.get("prefer_coherence_over_novelty", True):
        return {"ethics_note":"Metapreference: držím koherenci před novotou."}
    return {}
