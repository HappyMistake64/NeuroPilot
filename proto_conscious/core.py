
from __future__ import annotations
from typing import Dict, Any, List, Callable
import os, json, datetime, copy, unicodedata, threading

class Agent:
    def __init__(self, cfg: Dict[str,Any]):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.base = cfg.get("basepath") or os.path.dirname(__file__)
        self.values = cfg.get("values", {})
        self.metaprefs = cfg.get("metaprefs", {})
        self.state: Dict[str,Any] = {
            "basepath": self.base,
            "values": self.values,
            "metaprefs": self.metaprefs,
            "intero": {"energy":0.7, "stress":0.2, "joy":0.1, "frustration":0.0},
            "tasks": [],
            "culture_store": [],
            "context": [],
            "web_cfg": cfg.get("web_cfg", {}),
            "wm_cfg": cfg.get("wm_cfg", {}),
            "cons_cfg": cfg.get("cons_cfg", {})
        }
        self.mods: List[Callable[[Dict[str,Any]], Dict[str,Any]]] = []

    def register(self, fn): self.mods.append(fn)

    def chat(self, prompt:str)->str:
        with self.lock:
            return self._chat(unicodedata.normalize("NFC", prompt))

    def _chat(self, prompt):
        st = copy.deepcopy(self.state); st.update({"prompt":prompt})
        out: Dict[str,Any] = {}
        for fn in self.mods:
            delta = fn(dict(st)) or {}
            # apply special setters
            if "__set_tasks" in delta: 
                st["tasks"] = delta["__set_tasks"]; del delta["__set_tasks"]
            # merge normal deltas
            st.update(delta); out.update(delta)

        reply = out.get("reply") or out.get("candidate_reply") or "(…)"
        lines = [f"Odpověď (Obsah): {reply}"]
        if self.cfg.get("story_mode", True):
            lines.append(out.get("narrative_line","Narrativní já: (pozornost zapnuta)"))
        lines.append("---")
        for key, label in [
            ("coach","Doporučení"),
            ("question","Moje otázka"),
            ("identity_line","Identita"),
            ("wm_line","Pracovní paměť"),
            ("goal_line","Autonomní cíle"),
            ("sleep_line","Konsolidace"),
            ("social_line","Sociální já"),
            ("ethics_note","Etika"),
            ("critique","Reflexe"),
            ("world_event","Svět"),
            ("web_note","Web")
        ]:
            if out.get(key): lines.append(f"{label}: {out[key]}")

        # Preserve every state field, including working memory and rewritten config.
        transient = {"prompt", "candidate_reply", "reply", "web_text", "web_url"}
        self.state.update({key: value for key, value in st.items() if key not in transient and not key.endswith("_line")})
        self.state["context"] = (st.get("context", []) + [prompt])[-64:]
        self.values = self.state["values"]
        self.metaprefs = self.state["metaprefs"]
        return "\n".join(lines)
