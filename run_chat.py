#!/usr/bin/env python3
"""Offline rule-based agent; no model downloads or internet at startup."""
import importlib
import json
from pathlib import Path
from proto_conscious.core import Agent

MODULES = [
    ("language_module", "language_flex_module"),
    ("internet_batch", "internet_batch_module"),
    ("internet_sensor", "internet_sensor_module"),
    ("relevance_filter", "relevance_filter_module"),
    ("working_memory", "working_memory_module"),
    ("other_self", "other_self_module"),
    ("consolidation", "consolidation_module"),
    ("goal_gen", "goal_gen_module"),
    ("self_rewrite", "self_rewrite_module"),
    ("feedback_learning", "feedback_learning_module"),
    ("self_mod_module", "self_mod_module"),
    ("future_sim_module", "future_sim_module"),
    ("metapref_module", "metapref_module"),
    ("sensors_module", "sensors_module"),
    ("identity_persistence", "identity_persistence_module"),
]

def load_cfg(base):
    path = Path(base) / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(cfg, dict) or not isinstance(cfg.get("agent", {}), dict):
        raise ValueError("Neplatná konfigurace agenta.")
    return cfg, cfg.get("agent", {})

def create_agent():
    base = Path(__file__).resolve().parent
    _, config = load_cfg(base)
    config = dict(config)
    config.setdefault("basepath", str(base))
    agent = Agent(config)
    for module, function in MODULES:
        agent.register(getattr(importlib.import_module("proto_conscious." + module), function))
    return agent

def main():
    agent = create_agent()
    print("NeuroPilot — lokální pravidlový režim. Konec: exit; stav: :save_all / :load_all")
    try:
        while True:
            text = input("Ty: ").strip()
            if text.lower() in {"exit", "quit"}:
                break
            if text:
                print(agent.chat(text))
    except (EOFError, KeyboardInterrupt):
        pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
