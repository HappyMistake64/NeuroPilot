
from __future__ import annotations
from typing import Dict, Any
import re, random
def language_flex_module(state: Dict[str,Any]) -> Dict[str,Any]:
    prompt = str(state.get("prompt",""))
    words = re.findall(r"[A-Za-zÀ-ž0-9]{4,}", prompt.lower())
    topics=[]; seen=set()
    for w in words:
        if w in seen: continue
        seen.add(w); topics.append(w)
        if len(topics)>=3: break
    if not topics: topics=["téma","plán","krok"]
    bullets=", ".join(topics)
    plan="1) ujasnit cíl, 2) vybrat 1 další krok, 3) ověřit výsledek"
    hyp=f"klíčový prvek {topics[0]} je jasnost a měřitelnost"
    text = random.choice([
        f"Shrnutí: {bullets}. Doporučení: {plan}.",
        f"Pracovní hypotéza: {hyp}. Krátký plán: {plan}.",
        f"Směr: {bullets}. Začni malým pokusem a zaznamenej výsledek."
    ])
    base = state.get("candidate_reply","")
    if base: base += " "
    return {"candidate_reply": (base+text).strip(), "identity_line": f"Témata: {', '.join(topics)}"}
