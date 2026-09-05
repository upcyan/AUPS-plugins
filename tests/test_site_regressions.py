"""Isolated regression tests; never start host services or containers."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]

class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        modules = {}
        for name in ('review', 'review.modules', 'review.modules.traefik', 'review.modules.domainproxy', 'review.core'):
            modules[name] = types.ModuleType(name)
            modules[name].__path__ = []
        for name in ('config', 'errors', 'util'):
            modules['review.' + name] = types.ModuleType('review.' + name)
        modules['review.config'].plugin_dir = lambda name, kind: str(self.root / kind)
        modules['review.config'].get_plugin_params = lambda name: {}
        modules['review.errors'].AppError = RuntimeError
        modules['review.util'].has_cmd = lambda name: True
        modules['review.util'].run = lambda *a, **kw: self.fail('Unexpected external command')
        modules['review.core'].waf = types.SimpleNamespace(render_config=lambda: {})
        modules['review.core'].rproxy = types.SimpleNamespace(backend_list=lambda: {'backends': [{'name': 'caddy', 'capabilities': ['sites']}, {'name': 'other', 'capabilities': []}]})
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def load(self, plugin, name):
        module_name = 'review.modules.' + plugin + '.' + name
        spec = importlib.util.spec_from_file_location(module_name, ROOT / 'plugins' / plugin / 'module' / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def test_domainproxy_status_and_hooks(self):
        service = self.load('domainproxy', 'service')
        with patch.object(service.os.path, 'exists', return_value=False):
            self.assertEqual(service.status()['backends'], [{'name': 'caddy', 'title': 'caddy'}])
        api = self.load('domainproxy', 'api')
        for name in ('start', 'stop', 'remove'):
            self.assertIs(getattr(api, name), getattr(service, name))

    def test_tcp_save_update_delete_and_readonly_validation(self):
        api = self.load('traefik', 'api')
        api.start = lambda: None
        site = {'host': 'db.example.com', 'mode': 'tcp', 'target': 'localhost:5432', 'options': {'listen_port': 5432}}
        api._save([site])
        self.assertIn('address: :5432', (api._dir() / 'traefik.yml').read_text())
        self.assertIn('tcp0', (api._dir() / 'dynamic.yml').read_text())
        before = (api._dir() / 'traefik.yml').read_bytes()
        self.assertEqual(api.validate()['scope'], 'managed_sites')
        self.assertEqual(before, (api._dir() / 'traefik.yml').read_bytes())
        api.update_site(site['host'], options={'listen_port': 5433})
        self.assertIn('address: :5433', (api._dir() / 'traefik.yml').read_text())
        api.delete_site(site['host'])
        self.assertNotIn('tcp0', (api._dir() / 'traefik.yml').read_text())
        self.assertEqual(api._load(), [])

    def test_failed_start_restores_all_files(self):
        api = self.load('traefik', 'api')
        api.start = lambda: None
        api._save([])
        before = {p: p.read_bytes() for p in api._dir().iterdir() if p.is_file()}
        starts = []
        def start():
            starts.append(True)
            if len(starts) == 1:
                raise RuntimeError('container failed')
        api.start = start
        with self.assertRaisesRegex(RuntimeError, 'container failed'):
            api.create_site('example.com', target='localhost:8080')
        self.assertEqual(len(starts), 2)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_invalid_tcp_does_not_write(self):
        api = self.load('traefik', 'api')
        api.start = lambda: self.fail('Must not restart')
        for port in (0, 80, 443, 65536, 'bad'):
            with self.assertRaises(RuntimeError):
                api._save([{'host': 'db.example.com', 'mode': 'tcp', 'target': 'localhost:5432', 'options': {'listen_port': port}}])
        self.assertFalse(api._dir().exists())

if __name__ == '__main__':
    unittest.main()
