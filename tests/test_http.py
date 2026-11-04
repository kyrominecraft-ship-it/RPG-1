import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rpg.engine import Ollama
from rpg.store import Store
from rpg.web import make_server


class HTTPTests(unittest.TestCase):
    def test_real_adapter_through_http_with_fake_ollama(self):
        calls = []

        class OllamaStub(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(body)
                content = ('The door remains locked. You hear footsteps inside.' if 'format' not in body
                           else json.dumps({'approved': True, 'issues': [], 'updates': []}))
                result = json.dumps({'done': True, 'done_reason': 'stop', 'message': {'content': content}}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(result)))
                self.end_headers()
                self.wfile.write(result)

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'campaign')
            (store.root / 'Rules.txt').write_text('The door is locked.', encoding='utf-8')
            stub = ThreadingHTTPServer(('127.0.0.1', 0), OllamaStub)
            app = make_server(store, Ollama(f'http://127.0.0.1:{stub.server_port}'), 0)
            threads = []
            for server in (stub, app):
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                threads.append(thread)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = f'http://127.0.0.1:{app.server_port}'
            try:
                with opener.open(url + '/') as response:
                    self.assertIn('Your action', response.read().decode())
                with opener.open(url + '/chat.js') as response:
                    self.assertEqual(response.headers.get_content_type(), 'text/javascript')
                    self.assertIn('textContent', response.read().decode())
                request = urllib.request.Request(url + '/api/play', json.dumps({'action': 'Listen at the door.'}).encode(),
                                                  {'Content-Type': 'application/json', 'Origin': url})
                with opener.open(request) as response:
                    turn = json.load(response)
                self.assertEqual(turn['status'], 'approved')
                self.assertNotIn('audit', turn)
                self.assertEqual(len(calls), 2)
                self.assertIn('independently audit', calls[1]['messages'][0]['content'])
                with opener.open(url + '/api/state') as response:
                    state = json.load(response)
                self.assertEqual(len([e for e in state['events'] if e['kind'] == 'story']), 1)
                self.assertEqual(len(state['documents']), 1)
                self.assertEqual(state['version'], '0.1.1')
                request = urllib.request.Request(url + '/api/play', b'{}',
                    {'Content-Type': 'application/json', 'Origin': 'https://unrelated.example'})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    opener.open(request)
                self.assertEqual(error.exception.code, 403)
            finally:
                for server in (app, stub):
                    server.shutdown()
                    server.server_close()
                for thread in threads:
                    thread.join(timeout=3)

    def test_campaign_selection_profile_creation_and_confirmed_continuity_over_http(self):
        from rpg.campaigns import Campaigns
        from unittest.mock import patch
        from test_core import FakeModel, APPROVE, RESPONSE

        class AppModel(FakeModel):
            def generate(self, role, system, payload):
                if 'brief' in payload:
                    return '# Name\nMira\n# Private Interpretations\nShe distrusts the baron.'
                return super().generate(role, system, payload)

        with tempfile.TemporaryDirectory() as tmp:
            manager = Campaigns(Path(tmp) / 'campaigns')
            app = make_server(manager, AppModel([APPROVE]), 0)
            thread = threading.Thread(target=app.serve_forever, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = f'http://127.0.0.1:{app.server_port}'
            def request(path, payload=None):
                req = urllib.request.Request(url + '/api/' + path,
                    None if payload is None else json.dumps(payload).encode(), {'Content-Type': 'application/json'})
                with opener.open(req) as response:
                    return json.load(response)
            try:
                self.assertIsNone(request('state')['campaign'])
                created = request('campaign/create', {'name': 'Test campaign'})
                draft = request('profile/draft', {'name': 'Mira', 'template': 'Templates/Character_Template.txt', 'brief': 'tower keeper'})
                self.assertNotIn('Characters/Mira.txt', request('state')['documents'])
                request('profile/accept', {'draft': draft['id'], 'content': draft['content']})
                state = request('state')
                self.assertIn('Continuity/Characters/Mira.txt', state['documents'])
                turn = request('play', {'action': 'Speak to Mira'})
                self.assertTrue(turn['proposals'])
                request('updates', {'turn': turn['id']})
                self.assertIn(RESPONSE, request('state')['documents']['Continuity/Characters/Mira.txt']['content'])
                request('campaign/create', {'name': 'Second campaign'})
                self.assertNotIn('Characters/Mira.txt', request('state')['documents'])
                with patch('rpg.campaigns.choose_directory', return_value=created['campaign']):
                    request('campaign/browse', {})
                self.assertIn('Characters/Mira.txt', request('state')['documents'])
                rules = Path(created['campaign']) / 'Rules.txt'
                rules.write_text('Edited externally.', encoding='utf-8')
                self.assertEqual(request('state')['documents']['Rules.txt']['content'], 'Edited externally.')
            finally:
                app.shutdown()
                app.server_close()
                thread.join(timeout=3)
