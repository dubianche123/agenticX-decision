"""Privacy and offline regressions using invented inputs only."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
import engine
import mzt_common
from cost import call_cost
from sample_data import RULES, REPORT_TEXT, scripts

ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environ = patch.dict(os.environ, {
            'MZT_CONFIG_DIR': str(self.root / 'config'),
            'MZT_DATA_DIR': str(self.root / 'data'),
        })
        self.environ.start()
        for name in list(os.environ):
            if name.startswith('MZT_') and name not in ('MZT_CONFIG_DIR', 'MZT_DATA_DIR'):
                os.environ.pop(name)
        self.client = TestClient(app.app)
        self.mock = patch.object(app, 'MOCK', True)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.client.close()
        self.environ.stop()
        self.temp.cleanup()

    def test_clean_home_has_no_key_or_endpoint(self):
        self.assertIsNone(mzt_common.read_key())
        self.assertEqual(mzt_common.resolve_endpoint(), ('', ''))
        self.assertEqual(mzt_common.resolve_stage('vision')['model'], '')

    def test_global_environment_inherited_by_stages(self):
        with patch.dict(os.environ, {'MZT_LLM_MODEL': 'synthetic-model',
                                    'MZT_LLM_BASE_URL': 'https://provider.example/v1'}):
            cfg = mzt_common.resolve_stage('main')
            self.assertEqual(cfg['model'], 'synthetic-model')
            self.assertEqual(cfg['base_url'], 'https://provider.example/v1')

    def test_settings_never_echo_global_or_stage_secrets(self):
        profile = {'key': 'synthetic-global-secret', 'stages': {
            'vision': {'key': 'synthetic-stage-secret',
                       'base_url': 'https://user:synthetic-password@provider.example/v1?token=synthetic-query'}}}
        mzt_common.write_private(mzt_common.config_path('.mzt_demo_profile.json'), json.dumps(profile))
        response = self.client.get('/api/settings')
        self.assertEqual(response.status_code, 200)
        for value in ('synthetic-global-secret', 'synthetic-stage-secret', 'synthetic-password', 'synthetic-query'):
            self.assertNotIn(value, response.text)

    def test_key_files_restrict_permissions_and_urls_reject_secrets(self):
        response = self.client.post('/api/settings', json={'key': 'synthetic-local-secret',
             'base_url': 'https://provider.example/v1', 'model': 'synthetic-model'})
        self.assertEqual(response.status_code, 200)
        for name in ('.mzt_demo_key', '.mzt_demo_profile.json'):
            self.assertEqual(mzt_common.config_path(name).stat().st_mode & 0o777, 0o600)
        self.assertNotIn('synthetic-local-secret', self.client.get('/api/settings').text)
        self.assertEqual(self.client.post('/api/settings', json={
             'base_url': 'https://provider.example/v1?key=synthetic'}).status_code, 422)

    def test_traversal_and_symlink_outside_data_rejected(self):
        root = mzt_common.data_dir()
        root.mkdir()
        sibling = self.root / 'data-other'
        sibling.mkdir()
        (sibling / 'test.pdf').write_bytes(b'synthetic')
        (root / 'link').symlink_to(sibling, target_is_directory=True)
        for path in ('../data-other/test.pdf', 'link/test.pdf'):
            # Test the actual resolver; mock audits intentionally do not open files.
            with self.assertRaises(app.HTTPException):
                app.resolve_workspace('pdf:' + path)
            with self.assertRaises(ValueError):
                mzt_common.contained_path(root, path)

    def test_mock_sse_respects_selected_rules_without_network(self):
        with patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden')):
            response = self.client.post('/api/audit/run', json={'rule_ids': [RULES[0]['id']], 'mock': True})
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        items = [e for e in events if e['event'] == 'item_result']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['item_id'], RULES[0]['id'])
        self.assertFalse(items[0]['blocked'])
        self.assertEqual(items[0]['usage']['prompt_tokens'], 0)
        self.assertEqual(events[-1]['event'], 'eof')

    def test_custom_mock_rule_is_explicitly_blocked(self):
        rule = dict(RULES[0], id='custom')
        events = asyncio.run(self.collect(engine.audit_stream([rule], {'kind': 'demo'}, mock=True)))
        self.assertTrue(events[1]['blocked'])

    @staticmethod
    async def collect(stream):
        return [item async for item in stream]

    def test_missing_tool_evidence_and_bad_json_blocked(self):
        for output in ('not-json', '{}', '{"evidence":"synthetic"}'):
            self.assertTrue(engine.validate_item(output, [], require_tool=True, tool_name='check_test')['blocked'])

    def test_synthetic_quotes_and_arithmetic(self):
        for rule in RULES:
            output = json.loads(scripts()[rule['id']][-1]['final'])
            self.assertIn(output['evidence'].split('] ', 1)[1], REPORT_TEXT)
        self.assertAlmostEqual(call_cost(1000, 200, 0, 1, 2, .5), .0014)
        self.assertEqual(engine.check_evidence_count(3, 2, 2)['verdict'], '不合格')
        self.assertEqual(engine.check_evidence_count(3, 4, 2)['verdict'], '不合格')
        self.assertEqual(engine.check_evidence_count(3, 3, 2)['verdict'], '合格')

    def test_all_cli_mocks_work_without_data_credentials_or_network(self):
        for script in ('mztdemo.py', 'mztdemo_v2.py', 'mztdemo_v3_baseline.py'):
            bootstrap = '''import socket, runpy, sys
from pathlib import Path
import mzt_common
mzt_common.REPO_ROOT = Path(sys.argv[1])
def deny(*a, **kw):
    raise AssertionError("Network forbidden in offline mode")
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
script = sys.argv[2]
sys.argv = [script, "--mock"]
runpy.run_path(script, run_name="__main__")
'''
            result = subprocess.run([sys.executable, '-c', bootstrap, str(self.root), str(ROOT / script)],
                                    cwd=ROOT, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == '__main__':
    unittest.main()
