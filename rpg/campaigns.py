"""Campaign selection; no network or database is involved."""
from pathlib import Path
from .store import Store


class Campaigns:
    def __init__(self, home, selected=None):
        self.home = Path(home).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.current = selected

    def require(self):
        if not self.current:
            raise ValueError('Choose or create a campaign first')
        return self.current

    def list(self):
        return [{'name': p.name, 'path': str(p)} for p in sorted(self.home.iterdir()) if p.is_dir() and not p.is_symlink()]

    def select(self, path):
        root = Path(path).expanduser().resolve(strict=True)
        if not root.is_dir() or (root / '.git').exists() or (root / 'rpg' / 'engine.py').exists():
            raise ValueError('Choose a campaign folder, not the application code folder')
        store = Store(root)
        store.snapshot()  # Validate before changing the active campaign.
        self.current = store
        return store

    def create(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError('Enter a campaign name (1–80 characters)')
        if any(c in name for c in '<>:"/\\|?*') or name.endswith(('.', ' ')) or name in ('.', '..'):
            raise ValueError('Use a simple Windows folder name')
        if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}:
            raise ValueError('This name is reserved by Windows')
        root = self.home / name
        root.mkdir()  # Never replace an existing campaign.
        for directory in ('Characters', 'Continuity/Characters', 'Continuity', 'World', 'Templates'):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / 'Rules.txt').write_text('CAMPAIGN RULES\n\nAdjudicate impartially. Reward preparation and established capabilities.\nRoll only for meaningful uncertainty and consequences. Never invent player dice results.\nRespect established profiles, character-specific knowledge and the timeline.\n', encoding='utf-8')
        (root / 'Continuity' / 'World.txt').write_text('WORLD CONTINUITY\n\nWrite your initial situation here before playing.\n', encoding='utf-8')
        template = Path(__file__).parent.parent / 'examples' / 'Templates' / 'Character_Template.txt'
        (root / 'Templates' / 'Character_Template.txt').write_bytes(template.read_bytes())
        return self.select(root)


def choose_directory():
    # Tk runs in a child main thread, rather than the HTTP request worker.
    import json
    import subprocess
    import sys
    try:
        result = subprocess.run([sys.executable, '-m', 'rpg.picker'], capture_output=True,
                                text=True, timeout=300, check=True)
        return json.loads(result.stdout)['path']
    except Exception as exc:
        raise ValueError('Folder picker unavailable. Paste the campaign folder path in the app.') from exc
