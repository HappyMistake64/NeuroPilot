from pathlib import Path
from datetime import datetime, timezone

def sensors_module(state):
    raw = str(state.get("prompt", "")).strip()
    prompt = raw.lower()
    if prompt == ":time":
        return {"world_event": "Čas: " + datetime.now(timezone.utc).isoformat()}
    if prompt.startswith(":read "):
        if not state.get("basepath"):
            return {"world_event": "(bez basepath)"}
        base = Path(state["basepath"]).resolve()
        path = (base / raw.split(" ", 1)[1].strip()).resolve()
        if not path.is_relative_to(base):
            return {"world_event": "Čtení mimo projekt není povoleno."}
        try:
            with path.open(encoding="utf-8") as f:
                text = f.read(2000)
            return {"world_event": f"Senzor soubor: {path.name} → {len(text)} znaků načteno."}
        except (OSError, UnicodeError) as error:
            return {"world_event": f"Chyba čtení: {error}"}
    if prompt.startswith(":image "):
        return {"world_event": "Analýza obrázků zatím není implementována."}
    return {}
