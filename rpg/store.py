"""Readable folder campaigns. Sources stay editable; the event log is append-only."""
import hashlib
import json
import os
import threading
import uuid
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from pathlib import Path

from .files import campaign_lock, durable_write_new, locked_file

PERSPECTIVES = {'objective', 'belief', 'suspicion', 'assumption'}
TEMPLATE = '''CHARACTER CONTINUITY: {name}
Profile: Characters/{name}.txt

Profile and continuity are separate. Never change personality, history, or motivations
merely to fit narration. Entries below are appended only after player approval.
Objective facts are distinct from beliefs, suspicions, and assumptions.
Knowledge entries record when and how the character learned the information.
Unresolved contradictions must remain visible until explicitly resolved.
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


class Store:
    def __init__(self, folder):
        self.root = Path(folder).expanduser().resolve()
        if self.root.suffix.lower() in ('.sqlite3', '.db'):
            raise ValueError('Choose a campaign folder, not the old SQLite database')
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta = self.root / '.rpg'
        self._check_path(self.meta)
        self.meta.mkdir(exist_ok=True)
        for name in ('history', 'audits'):
            self._check_path(self.meta / name)
            (self.meta / name).mkdir(exist_ok=True)
        self.log = self.meta / 'events.jsonl'
        self.lock = threading.RLock()
        # Validate managed paths before following any user-created links.
        self._check_path(self.meta)
        self._check_path(self.log)

    def _check_path(self, path):
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('Campaign paths must stay inside the selected folder')
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
                raise ValueError('Links/junctions are not supported inside campaigns')

    @contextmanager
    def _guard(self):
        with self.lock:
            for path in (self.meta, self.meta / 'history', self.meta / 'audits', self.meta / 'lock', self.log):
                self._check_path(path)
            with campaign_lock(self.meta / 'lock'):
                yield

    def _events(self):
        if not self.log.exists():
            return []
        result, previous = [], ''
        for line in self.log.read_bytes().splitlines(keepends=True):
            if not line.endswith(b'\n'):
                raise ValueError('Incomplete event log: stop and restore a backup; no files were overwritten')
            event = json.loads(line)
            checksum = event.pop('hash')
            if event['id'] != len(result) + 1 or event['previous'] != previous or digest(encoded(event)) != checksum:
                raise ValueError('Event log integrity check failed; restore a complete backup')
            event['hash'] = checksum
            result.append(event)
            previous = checksum
        return result

    def _append(self, kind, payload):
        events = self._events()
        event = {'id': len(events) + 1, 'kind': kind, 'payload': payload,
                 'created': datetime.now(timezone.utc).isoformat(),
                 'previous': events[-1]['hash'] if events else ''}
        event['hash'] = digest(encoded(event))
        with self.log.open('ab') as stream:
            stream.write(json.dumps(event, ensure_ascii=False).encode('utf-8') + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        return event

    def _backup(self, data):
        checksum = digest(data)
        path = self.meta / 'history' / (checksum + '.txt')
        self._check_path(path)
        if not path.exists():
            durable_write_new(path, data)
        elif path.read_bytes() != data:
            raise ValueError('History object is damaged; restore a backup')
        return checksum

    def _scan(self):
        # Explicit profiles only. Incidental NPC names in narration never reach this code.
        profiles = self.root / 'Characters'
        if profiles.exists():
            self._check_path(profiles)
            for profile in sorted(profiles.iterdir()):
                self._check_path(profile)
                if profile.is_file() and profile.suffix.lower() == '.txt':
                    profile.read_bytes().decode('utf-8-sig')
                    target = self.root / 'Continuity' / 'Characters' / profile.name
                    self._check_path(target)
                    if not target.exists():
                        durable_write_new(target, TEMPLATE.format(name=profile.stem).encode('utf-8'))
        docs, warnings, identities = {}, [], set()
        for directory, dirs, files in os.walk(self.root, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)):
            parent = Path(directory)
            if parent == self.root:
                dirs[:] = [d for d in dirs if d.casefold() != '.rpg']
            for name in dirs + files:
                self._check_path(parent / name)
            for name in sorted(files):
                path = parent / name
                if path.suffix.lower() not in ('.txt', '.json'):
                    continue
                relative = path.relative_to(self.root).as_posix()
                if relative.casefold() in identities:
                    raise ValueError('Case-insensitive duplicate filenames are not supported on Windows')
                identities.add(relative.casefold())
                if relative.casefold().startswith('continuity/characters/'):
                    profile = profiles / path.name
                    if path.parent != self.root / 'Continuity' / 'Characters' or not profile.is_file() or profile.suffix.lower() != '.txt':
                        warnings.append(f'Not loaded: {relative} has no matching profile TXT file')
                        continue
                raw = path.read_bytes()
                if len(raw) > 200_000:
                    raise ValueError(f'{relative} exceeds 200 KB; split the source document')
                content = raw.decode('utf-8-sig')
                if path.suffix.lower() == '.json':
                    json.loads(content)
                docs[relative] = {'content': content, 'version': digest(raw)}
        return docs, warnings

    def _recover(self):
        events = self._events()
        completed = {e['payload']['transaction'] for e in events if e['kind'] in ('updates_applied', 'updates_conflicted')}
        for event in events:
            if event['kind'] != 'updates_prepared' or event['payload']['transaction'] in completed:
                continue
            pending = event['payload']
            try:
                self._write_changes(pending['changes'])
            except (ValueError, FileNotFoundError):
                self._append('updates_conflicted', {'transaction': pending['transaction'], 'turn': pending['turn'],
                             'message': 'External change or incomplete write; preserved files. Re-propose updates.'})
                continue
            self._append('updates_applied', pending)

    def _write_changes(self, changes):
        # Acquire every target before writing any. Windows denies concurrent editor saves.
        with ExitStack() as stack:
            streams = []
            for change in changes:
                path = self.root / change['document']
                self._check_path(path)
                stream = stack.enter_context(locked_file(path, exclusive_write=True))
                raw = stream.read()
                if digest(raw) not in (change['before'], change['after']):
                    self._backup(raw)
                    raise ValueError('A file changed after review; newer contents were preserved')
                streams.append((stream, raw, change))
            for stream, raw, change in streams:
                if digest(raw) == change['after']:
                    continue
                new = (self.meta / 'history' / (change['after'] + '.txt')).read_bytes()
                if digest(new) != change['after']:
                    raise ValueError('History object is damaged')
                stream.seek(0)
                stream.write(new)
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())

    def _sync(self):
        self._recover()
        docs, warnings = self._scan()  # Parse everything before adopting a source revision.
        versions = {name: doc['version'] for name, doc in docs.items()}
        old = {}
        for event in self._events():
            if event['kind'] == 'sources_changed':
                old = event['payload']['documents']
        if versions != old:
            for name, doc in docs.items():
                raw = (self.root / name).read_bytes()
                if digest(raw) != doc['version']:
                    raise ValueError('A source changed while loading; wait for your editor to finish saving')
                self._backup(raw)
            self._append('sources_changed', {'documents': versions, 'previous_documents': old})
        events = self._events()
        if any(e['kind'] == 'updates_conflicted' for e in events):
            warnings.append('An earlier update save conflicted. Review events.jsonl and current continuity; newer contents were preserved.')
        revision = digest(encoded({'documents': versions, 'stories': [e['hash'] for e in events if e['kind'] == 'story']}))
        return {'documents': docs, 'events': events, 'revision': revision, 'warnings': warnings,
                'campaign': str(self.root), 'name': self.root.name,
                'continuity_targets': [n for n in docs if n.casefold().startswith('continuity/') and n.lower().endswith('.txt')]}

    def snapshot(self):
        with self._guard():
            return self._sync()

    def _turns(self):
        turns = {}
        for event in self._events():
            p = event['payload']
            if event['kind'] in ('turn_started', 'turn_finished', 'story', 'proposals_ready', 'turn_reviewed'):
                turns[p['turn']['id']] = p['turn']
            elif event['kind'] in ('updates_applied', 'updates_conflicted', 'updates_declined'):
                if p['turn'] in turns:
                    turns[p['turn']]['proposals'] = []
        return turns

    def turn(self, turn):
        with self._guard():
            row = self._turns().get(turn)
            if not row:
                raise ValueError('Unknown turn')
            return row

    def pending_updates(self):
        with self._guard():
            return [t for t in self._turns().values() if t['status'] == 'approved' and t['proposals']]

    def paused_turn(self):
        with self._guard():
            return next((t for t in self._turns().values() if t['status'] == 'paused'), None)

    def begin_turn(self, action, revision):
        with self._guard():
            turn = {'id': uuid.uuid4().hex, 'action': action, 'status': 'running', 'base_revision': revision,
                    'audit': [], 'response': None, 'proposals': [], 'continuity_audit': []}
            self._append('turn_started', {'turn': turn})
            return turn['id']

    def finish_turn(self, turn, status, audit, response=None, proposals=None):
        with self._guard():
            row = self._turns()[turn]
            if row['status'] != 'running':
                raise ValueError('Turn already finished')
            if status == 'approved' and self._sync()['revision'] != row['base_revision']:
                raise ValueError('Campaign files changed during generation; draft not saved. Retry with the new sources.')
            row.update(status=status, audit=audit, response=response, proposals=[])
            self._append('story' if status == 'approved' else 'turn_finished', {'turn': row})
            durable_write_new(self.meta / 'audits' / (turn + '.json'), encoded(row))

    def set_proposals(self, turn, proposals, revision, audit):
        with self._guard():
            row = self._turns()[turn]
            if row['status'] != 'approved' or self._sync()['revision'] != revision:
                raise ValueError('Sources changed during continuity review; request fresh proposals')
            row.update(proposals=proposals, proposal_revision=revision, continuity_audit=audit)
            self._append('proposals_ready', {'turn': row})

    def resume(self, turn):
        with self._guard():
            row = self._turns().get(turn)
            if not row or row['status'] != 'paused':
                raise ValueError('Turn is not paused')
            row['status'] = 'reviewed'
            self._append('turn_reviewed', {'turn': row})

    def decline_updates(self, turn):
        with self._guard():
            if turn not in self._turns():
                raise ValueError('Unknown turn')
            self._append('updates_declined', {'turn': turn})

    def accept_updates(self, turn):
        with self._guard():
            snapshot = self._sync()
            row = self._turns().get(turn)
            if not row or row['status'] != 'approved' or not row['proposals']:
                raise ValueError('No pending updates from an approved turn')
            if snapshot['revision'] != row['proposal_revision']:
                raise ValueError('Campaign changed since these proposals. No files overwritten. Request fresh proposals.')
            changes = []
            for update in row['proposals']:
                name = update['document']
                if name not in snapshot['continuity_targets']:
                    raise ValueError('Only registered continuity TXT files can be updated')
                old = (self.root / name).read_bytes()
                if digest(old) != snapshot['documents'][name]['version']:
                    raise ValueError('File changed; no updates saved')
                section = f'\n\n=== Approved event / turn {turn} ===\n'
                for entry in update['entries']:
                    section += (f"[{entry['perspective'].upper()} / {entry['category']}] {entry['statement']}\n"
                                f"Source: approved turn {turn}\nEvidence: {entry['evidence']}\n"
                                f"Learned when: {entry['learned_when']}\nLearned how: {entry['learned_how']}\n\n")
                new = old + section.encode('utf-8')
                changes.append({'document': name, 'before': self._backup(old), 'after': self._backup(new)})
            pending = {'transaction': uuid.uuid4().hex, 'turn': turn, 'changes': changes}
            self._append('updates_prepared', pending)  # Durable player-approved write intent.
            try:
                self._write_changes(changes)
            except (ValueError, FileNotFoundError):
                self._append('updates_conflicted', pending)
                raise
            self._append('updates_applied', pending)
            self._sync()

    def save_profile_draft(self, document, content, revision, template):
        with self._guard():
            draft = {'id': uuid.uuid4().hex, 'document': document, 'content': content,
                     'base_revision': revision, 'template': template}
            self._append('profile_draft', {'draft': draft})  # Noncanonical, no source file is created.
            return draft

    def profile_drafts(self):
        with self._guard():
            drafts = {}
            for event in self._events():
                if event['kind'] == 'profile_draft':
                    draft = event['payload']['draft']
                    drafts[draft['id']] = draft
                elif event['kind'] in ('profile_accepted', 'profile_declined'):
                    drafts.pop(event['payload']['draft'], None)
            return list(drafts.values())

    def accept_profile(self, draft_id, edited_content):
        with self._guard():
            draft = next((d for e in self._events() if e['kind'] == 'profile_draft'
                          for d in [e['payload']['draft']] if d['id'] == draft_id), None)
            if not draft or any(e['kind'] in ('profile_accepted', 'profile_declined') and e['payload']['draft'] == draft_id for e in self._events()):
                raise ValueError('No pending profile draft')
            snapshot = self._sync()
            if snapshot['revision'] != draft['base_revision']:
                raise ValueError('Campaign changed since this draft. Request a fresh draft to review current sources.')
            if not isinstance(edited_content, str) or not edited_content.strip() or len(edited_content.encode()) > 20000:
                raise ValueError('Profile needs 1–20000 UTF-8 bytes')
            path = self.root / draft['document']
            self._check_path(path)
            if any(n.casefold() == draft['document'].casefold() for n in snapshot['documents']):
                raise ValueError('Profile already exists; it was not overwritten')
            durable_write_new(path, edited_content.encode('utf-8'))
            self._append('profile_accepted', {'draft': draft_id, 'document': draft['document']})
            self._sync()  # Creates separate blank continuity only after a profile actually exists.

    def decline_profile(self, draft_id):
        with self._guard():
            self._append('profile_declined', {'draft': draft_id})

    def record_proposal_failure(self, turn, audit):
        with self._guard():
            row = self._turns()[turn]
            if row['status'] != 'approved':
                raise ValueError('Only approved turns can have continuity proposals')
            row.update(proposals=[], continuity_audit=audit)
            self._append('proposals_ready', {'turn': row})
