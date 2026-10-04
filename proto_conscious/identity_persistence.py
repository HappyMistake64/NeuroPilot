from pathlib import Path
from storage import JsonStore

KEYS = ("intero", "values", "metaprefs", "tasks", "culture_store", "wm_state", "cons_cfg", "wm_cfg", "context", "other_mem")

def identity_persistence_module(state):
    prompt = str(state.get("prompt", "")).strip().lower()
    if prompt not in {":save_all", ":load_all"} or not state.get("basepath"):
        return {}
    path = Path(state["basepath"]) / "state" / "agent_state_full.json"
    store = JsonStore(path, {})
    if prompt == ":save_all":
        store.write({key: state[key] for key in KEYS if key in state})
        return {"reply": "Identita uložena (full)."}
    if not path.exists():
        return {"reply": "Nenalezen žádný uložený stav."}
    try:
        blob = store.read()
        if not isinstance(blob, dict):
            raise ValueError("Stav musí být objekt.")
        # Old versions used aliases for culture and working memory.
        for old, new in (("culture", "culture_store"), ("wm", "wm_state")):
            if old in blob and new not in blob:
                blob[new] = blob[old]
        for key, value in blob.items():
            expected = list if key in {"tasks", "culture_store", "wm_state", "context"} else dict
            if key in KEYS and not isinstance(value, expected):
                raise ValueError(f"Neplatné pole {key}.")
        return dict({key: blob[key] for key in KEYS if key in blob}, reply="Identita načtena.")
    except (ValueError, OSError) as error:
        return {"reply": f"Stav nelze načíst: {error}"}
