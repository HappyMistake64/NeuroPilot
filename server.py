"""NeuroPilot local planner. Run one process on loopback."""
import json
from web_errors import public_error
import os
import uuid
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, request, send_from_directory, jsonify, Response
from werkzeug.exceptions import HTTPException
from chat_wrapper import chat as agent_chat
from storage import JsonStore

BASE = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE / "public"))
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
DATA_FILE = Path(os.environ.get("NEUROPILOT_DATA", BASE / "data.json"))

def iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Datum musí mít formát YYYY-MM-DD.")
    return value

def validate_data(data):
    if not isinstance(data, dict):
        raise ValueError("Import musí být objekt JSON.")
    out = {}
    for key, field in (("notes", "text"), ("tasks", "text"), ("habits", "title")):
        entries = data.get(key, [] if key == "habits" else None)
        if not isinstance(entries, list) or len(entries) > 10000:
            raise ValueError(f"Neplatná kolekce {key}.")
        seen = set()
        for row in entries:
            if not isinstance(row, dict) or not isinstance(row.get(field), str) or not row[field].strip() or len(row[field]) > 20000:
                raise ValueError(f"Neplatný záznam v {key}.")
            rid = row.get("id")
            if type(rid) not in (int, str) or not str(rid) or str(rid) in seen:
                raise ValueError(f"Neplatné nebo duplicitní ID v {key}.")
            seen.add(str(rid))
            if key == "habits":
                records = row.get("records", [])
                if not isinstance(records, list) or len(records) > 10000:
                    raise ValueError("Neplatné záznamy návyku.")
                row["records"] = sorted(set(iso_date(x) for x in records), reverse=True)
            if key == "tasks" and type(row.get("done", False)) is not bool:
                raise ValueError("Stav úkolu musí být boolean.")
            if key == "notes" and not isinstance(row.get("ai", ""), str):
                raise ValueError("Odpověď musí být text.")
        out[key] = entries
    return out

store = JsonStore(DATA_FILE, {"notes": [], "tasks": [], "habits": []}, validate_data)

def now():
    return datetime.now(timezone.utc).isoformat()

def body():
    value = request.get_json()
    if not isinstance(value, dict):
        raise ValueError("Požadavek musí být objekt JSON.")
    return value

def text_field(value, key):
    text = value.get(key)
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise ValueError(f"Pole {key} musí obsahovat text (nejvýše 20 000 znaků).")
    return text.strip()

def origin_parts(value):
    """An Origin is only a scheme, host and optional port, never a URL path."""
    parts = urlsplit(value)
    if (parts.scheme not in {'http', 'https'} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path or parts.query or parts.fragment):
        raise ValueError('Invalid origin')
    return parts.scheme, parts.hostname.lower(), parts.port or (443 if parts.scheme == 'https' else 80)

@app.before_request
def local_origin():
    try:
        expected = origin_parts(request.scheme + '://' + request.host)
        if expected[1] not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('Non-local host')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if request.headers.get('Sec-Fetch-Site') in {'cross-site', 'same-site'}:
                raise ValueError('Cross-origin browser request')
            origin = request.headers.get('Origin')
            if origin is not None and origin_parts(origin) != expected:
                raise ValueError('Origin mismatch')
    except ValueError:
        return jsonify(error='Povoleno pouze lokální připojení ze stejného původu.'), 403

@app.after_request
def security_headers(response):
    # Both frontends use external scripts; inline styles remain for existing CSS.
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if response.is_json or request.path == '/export':
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.errorhandler(ValueError)
def invalid(error):
    return jsonify(error=public_error(error)), 400

@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/app.js")
def javascript():
    return send_from_directory(app.static_folder, "app.js")

@app.route("/health")
def health():
    return jsonify(ok=True, version="3.4.0", agent="local_rules", model=False)

@app.route("/think", methods=["POST"])
def think():
    text = text_field(body(), "text")
    out = agent_chat(text, timeout=30)
    note = dict(id=uuid.uuid4().hex, text=text, ai=out, created_at=now())
    store.update(lambda data: data["notes"].insert(0, note))
    return jsonify(note=note)

@app.route("/notes")
def notes():
    return jsonify(store.read()["notes"])

@app.route("/tasks", methods=["GET", "POST"])
def tasks():
    if request.method == "GET":
        return jsonify(store.read()["tasks"])
    task = dict(id=uuid.uuid4().hex, text=text_field(body(), "text"), created_at=now(), done=False)
    store.update(lambda data: data["tasks"].insert(0, task))
    return jsonify(task=task), 201

@app.route("/habits", methods=["GET", "POST"])
def habits():
    if request.method == "GET":
        return jsonify(store.read()["habits"])
    habit = dict(id=uuid.uuid4().hex, title=text_field(body(), "title"), created_at=now(), records=[])
    store.update(lambda data: data["habits"].insert(0, habit))
    return jsonify(habit=habit), 201

def find(data, collection, rid):
    from werkzeug.exceptions import NotFound
    row = next((x for x in data[collection] if str(x["id"]) == rid), None)
    if row is None:
        raise NotFound("Záznam nenalezen.")
    return row

@app.route("/tasks/<rid>/toggle", methods=["POST"])
def task_toggle(rid):
    def change(data):
        row = find(data, "tasks", rid)
        row["done"] = not row.get("done", False)
        return row
    return jsonify(task=store.update(change))

@app.route("/<collection>/<rid>", methods=["DELETE"])
def delete(collection, rid):
    if collection not in {"notes", "tasks", "habits"}:
        return jsonify(error="Neznámá kolekce."), 404
    def change(data):
        data[collection].remove(find(data, collection, rid))
    store.update(change)
    return jsonify(ok=True)

@app.route("/habits/<rid>/toggle", methods=["POST"])
def habit_toggle(rid):
    day = iso_date(body().get("date", date.today().isoformat()))
    def change(data):
        row = find(data, "habits", rid)
        if day in row["records"]:
            row["records"].remove(day)
        else:
            row["records"].append(day)
            row["records"].sort(reverse=True)
        return row
    return jsonify(habit=store.update(change))

@app.route("/habits/<rid>/stats/<int:days>")
def stats(rid, days):
    if not 1 <= days <= 366:
        raise ValueError("Počet dní musí být 1–366.")
    row = find(store.read(), "habits", rid)
    return jsonify([dict(date=(date.today()-timedelta(days=i)).isoformat(), done=(date.today()-timedelta(days=i)).isoformat() in row["records"]) for i in range(days-1, -1, -1)])

@app.route("/export")
def export_data():
    return Response(json.dumps(store.read(), ensure_ascii=False, indent=2), mimetype="application/json", headers={"Content-Disposition": 'attachment; filename="neuropilot-data.json"'})

@app.route("/import", methods=["POST"])
def import_data():
    store.write(validate_data(body()))
    return jsonify(ok=True)

from rsi.web import blueprint as rsi_blueprint
app.register_blueprint(rsi_blueprint)

if __name__ == "__main__":
    store.read()
    app.run(host="127.0.0.1", port=5000, debug=False)
