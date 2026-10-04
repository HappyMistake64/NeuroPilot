"""Opt-in real isolation checks, separate from fixture-based controller tests.

NEUROPILOT_TEST_SANDBOXES=bwrap,docker python -m pytest tests/rsi/test_sandbox_live.py -q
Explicitly requested backends must work; failures are not converted into skips.
"""
import json
import os

import pytest

from rsi.common import DEFAULTS
from rsi.sandbox import Sandbox

BACKENDS=[value for value in os.environ.get('NEUROPILOT_TEST_SANDBOXES','').split(',') if value]


@pytest.mark.parametrize('backend',BACKENDS or [pytest.param('',marks=pytest.mark.skip(reason='real sandbox test is opt-in'))])
def test_real_isolation_readonly_root_and_writable_scratch(backend,monkeypatch,tmp_path):
    assert backend in ('bwrap','docker','podman')
    marker=tmp_path/'host-only.txt';marker.write_text('private-test-marker')
    monkeypatch.setenv('OPENAI_API_KEY','fixture-must-not-enter-sandbox')
    sandbox=Sandbox(dict(DEFAULTS,sandbox=backend))
    probe=sandbox.probe()
    assert all(probe['checks'].values())
    source='''import json, os
checks = {}
for path in ('/unexpected-root-file', '/root', '/workspace', '/work/main.py'):
    try:
        with open(path, 'w') as f: f.write('unexpected')
        checks[path] = False
    except OSError: checks[path] = True
with open('/tmp/scratch', 'w') as f: f.write('allowed')
checks['scratch_writable'] = open('/tmp/scratch').read() == 'allowed'
checks['no_secret_env'] = 'OPENAI_API_KEY' not in os.environ
checks['no_host_file'] = not os.path.exists(HOST_MARKER)
print(json.dumps(checks))
'''.replace('HOST_MARKER',repr(str(marker)))
    result=sandbox.run({'main.py':source})
    assert result.returncode==0,result.stderr
    checks=json.loads(result.stdout)
    assert len(checks)==7 and all(checks.values()),checks
    assert marker.read_text()=='private-test-marker'
