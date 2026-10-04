"""Run a quick offline check without altering user state."""
import tempfile
from run_chat import create_agent, MODULES

def main():
    with tempfile.TemporaryDirectory() as base:
        agent = create_agent()
        agent.state['basepath'] = base
        assert len(agent.mods) == len(MODULES)
        for prompt in ('Ahoj', ':rewrite working_memory.slots 3', ':self truth 0.8', ':save_all', ':load_all'):
            response = agent.chat(prompt)
            assert response
            print(prompt, '\n', response, '\n')
    print('OK: agent, moduly, paměť, změny nastavení a uložení/načtení stavu.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
