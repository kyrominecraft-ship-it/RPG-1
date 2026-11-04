import argparse
import threading
import webbrowser
from pathlib import Path
from .campaigns import Campaigns
from .engine import Ollama
from .web import make_server


def main():
    parser = argparse.ArgumentParser(description='Local folder-based RPG')
    parser.add_argument('--campaigns', default=str(Path.home() / 'Documents' / 'LocalRPG' / 'Campaigns'))
    parser.add_argument('--campaign', help='Optional initial campaign folder')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--gm-model', default='qwen2.5:7b')
    parser.add_argument('--admin-model', default='qwen2.5:7b')
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    manager = Campaigns(args.campaigns)
    if args.campaign:
        manager.select(args.campaign)
    app = make_server(manager, Ollama(gm=args.gm_model, admin=args.admin_model), args.port)
    print(f'Local RPG listening on port {app.server_port}. Keep this window open. Ctrl+C stops the app.', flush=True)
    if args.open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f'http://127.0.0.1:{app.server_port}')).start()
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.server_close()


if __name__ == '__main__':
    main()
