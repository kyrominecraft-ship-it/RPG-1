"""Loopback-only, single-player HTTP interface. No external assets or packages."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .version import APP_VERSION


def make_server(store, model, port=8000):
    from .engine import Engine
    from .templates import template_report, draft_profile
    from .campaigns import Campaigns
    from . import campaigns as campaign_module
    manager = store if isinstance(store, Campaigns) else Campaigns(store.root.parent, store)
    mutation_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not put player actions into access logs.

        def send(self, status, content, content_type='application/json'):
            body = content.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',
                                                  f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, '{}')
            if self.path == '/':
                return self.send(200, Path(__file__).with_name('index.html').read_text(encoding='utf-8'), 'text/html')
            if self.path == '/chat.js':
                return self.send(200, Path(__file__).with_name('chat.js').read_text(encoding='utf-8'), 'text/javascript')
            if self.path == '/api/state':
                try:
                    if manager.current:
                        active = manager.require()
                        state = active.snapshot()
                        state['paused'] = active.paused_turn()
                        state['pending_updates'] = active.pending_updates()
                        state['template_report'] = template_report(state)
                        state['profile_drafts'] = active.profile_drafts()
                    else:
                        state = {'documents': {}, 'events': [], 'paused': None, 'pending_updates': [], 'warnings': [], 'campaign': None}
                    state['version'] = APP_VERSION
                    state['campaigns'] = manager.list()
                    state['campaign_home'] = str(manager.home)
                    return self.send(200, json.dumps(state))
                except (ValueError, OSError) as exc:
                    return self.send(400, json.dumps({'error': str(exc)}))
            self.send(404, '{}')

        def do_POST(self):
            allowed_origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if (not self.valid_host() or self.headers.get('Origin') not in allowed_origins | {None}
                    or self.headers.get('Content-Type') != 'application/json'):
                return self.send(403, json.dumps({'error': 'Local JSON requests only'}))
            if not mutation_lock.acquire(blocking=False):
                return self.send(409, json.dumps({'error': 'Another operation is in progress'}))
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 100000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Request must be an object')
                if self.path == '/api/campaign/select':
                    result = {'campaign': str(manager.select(body['path']).root)}
                elif self.path == '/api/campaign/create':
                    result = {'campaign': str(manager.create(body['name']).root)}
                elif self.path == '/api/campaign/browse':
                    path = campaign_module.choose_directory()
                    result = {'campaign': str(manager.select(path).root) if path else None}
                else:
                    active = manager.require()
                    engine = Engine(active, model)
                    if self.path == '/api/play':
                        result = engine.play(body.get('action'))
                        if result['status'] == 'approved':
                            result['retrieval_mode'] = result['audit'][-1].get('gm_retrieval', {}).get('mode', 'full')
                            result.pop('audit')
                    elif self.path == '/api/profile/draft':
                        result = draft_profile(active, model, body.get('name'), body.get('template'), body.get('brief'))
                    elif self.path == '/api/profile/accept':
                        active.accept_profile(str(body['draft']), body.get('content'))
                        result = {'ok': True}
                    elif self.path == '/api/profile/decline':
                        active.decline_profile(str(body['draft']))
                        result = {'ok': True}
                    elif self.path == '/api/updates':
                        active.accept_updates(str(body['turn']))
                        result = {'ok': True}
                    elif self.path == '/api/updates/retry':
                        result = engine.propose_updates(str(body['turn']))
                        result.pop('audit')
                    elif self.path == '/api/updates/decline':
                        active.decline_updates(str(body['turn']))
                        result = {'ok': True}
                    elif self.path == '/api/resume':
                        active.resume(str(body['turn']))
                        result = {'ok': True}
                    else:
                        return self.send(404, '{}')
                self.send(200, json.dumps(result))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.send(400, json.dumps({'error': str(exc)}))
            except Exception:
                self.send(500, json.dumps({'error': 'File operation failed; inspect the campaign folder and close any busy editor before retrying'}))
            finally:
                mutation_lock.release()

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)
