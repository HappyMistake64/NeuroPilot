"""Mutable agent policy. Executed only inside a verified sandbox."""
import json

def build_context(payload):
    if payload['mode'] == 'propose':
        return json.dumps({
            'goal': 'Improve your own build_context strategy from the development evidence. Return a complete Python strategy module and a concrete hypothesis.',
            'current_strategy': payload['source'],
            'development_evidence': payload['evidence'],
            'contract': 'Define build_context(payload) -> str for modes solve and propose. Preserve the ability to propose further strategies. Maximum 200 changed lines. Only this strategy module is mutable.',
        }, ensure_ascii=False)
    return json.dumps({
        'goal': payload['task']['instruction'],
        'files': payload['files'],
        'public_checks': payload['task']['public'],
        'observations': payload['observations'],
        'remaining_steps': payload['remaining_steps'],
        'advice': 'Inspect the specification and current code, implement a general solution, use public tests when useful and finish. Do not hardcode examples.',
    }, ensure_ascii=False)
