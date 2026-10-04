"""Serialized lazy agent access with bounded requests and no late-result leak."""
import logging
import queue
import threading
from concurrent.futures import Future, TimeoutError
from run_chat import create_agent

_agent = None
_worker = None
_lock = threading.Lock()
_requests = queue.Queue(maxsize=16)


def _loop():
    while True:
        future, text = _requests.get()
        try:
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(_agent.chat(text))
                except Exception as error:
                    future.set_exception(error)
        finally:
            _requests.task_done()


def _init_agent_safe():
    global _agent, _worker
    with _lock:
        if _worker is None:
            _agent = create_agent()
            _worker = threading.Thread(target=_loop, daemon=True, name="neuropilot-agent")
            _worker.start()


def chat(text, timeout=60):
    _init_agent_safe()
    future = Future()
    try:
        _requests.put_nowait((future, text))
        return future.result(timeout=timeout)
    except queue.Full:
        return "Agent je vytížený. Zkus dotaz později."
    except TimeoutError:
        future.cancel()
        return "Časový limit agenta vypršel. Probíhající výpočet může ještě dobíhat."
    except Exception:
        logging.exception("Agent chat failed")
        return "Agent narazil na chybu. Podrobnosti jsou v serverovém výpisu."
