"""Optional text-model tools. Import is offline and never starts a UI."""
import json
import os
import re
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from storage import JsonStore
from web_tools import fetch_bytes, clean_text

BASE = Path(__file__).resolve().parent
MEMORY_PATH = BASE / "memory.json"
MEMORY = JsonStore(MEMORY_PATH, {"notes": [], "history": []})
PERSONA = "Jsi NeuroPilot, český asistent pro plánování a tvorbu. Jasně rozlišuj návrh od skutečně provedené akce."
_pipe = None
_model_lock = threading.Lock()

def load_memory():
    return MEMORY.read()

def save_memory(data):
    MEMORY.write(data)

def memory_add(title, body):
    note = dict(ts=datetime.now(timezone.utc).isoformat(), title=title, body=body)
    MEMORY.update(lambda data: data["notes"].insert(0, note))

def llm(prompt, max_len=200):
    global _pipe
    model = os.environ.get("NEUROPILOT_MODEL", "").strip()
    if not model:
        raise RuntimeError("Model není nastaven. Zadej NEUROPILOT_MODEL a nainstaluj requirements-ai.txt.")
    with _model_lock:
        if _pipe is None:
            from transformers import pipeline
            _pipe = pipeline("text-generation", model=model, device=-1)
        # Reserve space for generated tokens instead of exceeding model context.
        if hasattr(_pipe, "tokenizer") and hasattr(_pipe, "model"):
            tokenizer = _pipe.tokenizer
            config = _pipe.model.config
            limits = [getattr(config, key, None) for key in ("max_position_embeddings", "n_positions")]
            limits.append(getattr(tokenizer, "model_max_length", None))
            limits = [value for value in limits if isinstance(value, int) and 0 < value < 1000000]
            context = min(limits) if limits else 4096
            if not 0 < max_len < context:
                raise ValueError(f"Model má kontext {context} tokenů; požadovaný výstup {max_len} je příliš dlouhý.")
            previous = tokenizer.truncation_side
            try:
                tokenizer.truncation_side = "left"
                tokens = tokenizer.encode(prompt, max_length=context-max_len, truncation=True, add_special_tokens=False)
                prompt = tokenizer.decode(tokens, skip_special_tokens=True)
            finally:
                tokenizer.truncation_side = previous
        result = _pipe(prompt, max_new_tokens=max_len, do_sample=True, num_return_sequences=1, return_full_text=False)
    return result[0]["generated_text"].strip()

def fetch_url(url):
    _, data = fetch_bytes(url, timeout=10)
    return clean_text(data)[:10000]

def summarize(text):
    return llm(f"{PERSONA}\nShrň následující text do 5 vět:\n{text}\nShrnutí:", 250)

def chat_fn(msg, explain=False):
    if not isinstance(msg, str) or not msg.strip() or len(msg) > 20000:
        raise ValueError("Napiš dotaz do 20 000 znaků.")
    history = load_memory()["history"][-3:]
    response = llm(f"{PERSONA}\nHistorie: {json.dumps(history, ensure_ascii=False)}\nUživatel: {msg}\nAI:", 300)
    if explain:
        response += "\n\n" + llm(f"Stručně zdůvodni tuto odpověď bez tvrzení o provedených akcích: {response}", 100)
    def append(data):
        data["history"].append(dict(q=msg, a=response, ts=datetime.now(timezone.utc).isoformat()))
        data["history"] = data["history"][-1000:]
    MEMORY.update(append)
    return response

def autonomy_run(goal, steps="4", explain=False):
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 20000:
        raise ValueError("Zadej cíl do 20 000 znaků.")
    if not re.fullmatch(r"[1-8]", str(steps).strip()):
        raise ValueError("Počet kroků musí být 1–8.")
    count = int(steps)
    raw = llm(f"{PERSONA}\nRozděl tento cíl do {count} kroků. Jeden krok na řádek:\n{goal}\nPlán:", 300)
    plan = [re.sub(r"^\s*(?:\d+[.)]|[-•])\s*", "", x).strip() for x in raw.splitlines() if x.strip()][:count]
    if not plan:
        raise RuntimeError("Model nevytvořil plán.")
    results = []
    for step in plan:
        # Model-generated URLs do not trigger network calls. Research is explicit.
        result = llm(f"{PERSONA}\nNavrhni konkrétní řešení kroku, nic nespouštěj: {step}\nNávrh:", 300)
        memory_add("Návrh kroku", result)
        results.append(f"KROK: {step}\nNÁVRH: {result}")
    output = f"Cíl: {goal}\nRežim: textové návrhy, bez provádění příkazů.\n\n" + "\n\n".join(results)
    if explain:
        output += "\n\n" + llm(f"Stručně zdůvodni plán: {raw}", 100)
    return output

def fetch_and_sum(url):
    text = fetch_url(url)
    summary = summarize(text)
    memory_add(f"Web studie: {url}", summary)
    return text, summary

def project_zip(name, spec):
    if not isinstance(name, str) or not re.fullmatch(r"[\w -]{1,80}", name) or not name.strip():
        raise ValueError("Název musí mít 1–80 písmen, číslic, mezer, pomlček nebo podtržítek.")
    if not isinstance(spec, str) or not spec.strip() or len(spec) > 20000:
        raise ValueError("Zadej specifikaci do 20 000 znaků.")
    response = llm(f"{PERSONA}\nVytvoř projekt '{name}': {spec}\nSoubory zapisuj takto:\n--FILENAME: cesta\nobsah\n--END\n", 1500)
    files = {}
    for filename, body in re.findall(r"--FILENAME:\s*([^\n]+)\n(.*?)--END", response, re.S):
        filename = filename.strip()
        path = PurePosixPath(filename)
        if path.is_absolute() or '..' in path.parts or '\\' in filename or ':' in filename or '\x00' in filename or not path.parts:
            raise ValueError("Model navrhl nebezpečnou cestu souboru.")
        if path.as_posix() in files:
            raise ValueError("Model navrhl duplicitní soubor.")
        files[path.as_posix()] = body.strip()
    if not files or len(files) > 100 or sum(len(v.encode('utf-8')) for v in files.values()) > 2_000_000:
        raise RuntimeError("Model nevytvořil platnou sadu souborů. Prázdný ZIP nebude vydán.")
    output = BASE / "generated"
    output.mkdir(exist_ok=True)
    zip_path = output / f"{name.strip().replace(' ', '_')}-{uuid.uuid4().hex[:12]}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, body in files.items():
            archive.writestr(filename, body)
    return str(zip_path)
