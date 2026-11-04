import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rpg.engine import Engine, validate_updates, canonical_sources
from rpg.store import Store, digest

APPROVE = {'approved': True, 'issues': [], 'updates': []}
REJECT = {'approved': False, 'issues': [{'problem': 'Wrong location', 'source': 'document:Characters/Mira.txt',
          'quote': 'Mira is in the tower.', 'correction': 'Keep Mira in the tower.'}], 'updates': []}
RESPONSE = 'Mira promises the scout a meeting at dusk.'
UPDATE = {'document': 'Continuity/Characters/Mira.txt', 'entries': [
    {'category': 'promise', 'perspective': 'objective', 'statement': RESPONSE,
     'evidence': RESPONSE, 'learned_when': 'dusk', 'learned_how': 'Mira speaks to the scout'}]}


class FakeModel:
    def __init__(self, reviews=(), updates=None, callback=None):
        self.reviews, self.calls = iter(reviews), []
        self.updates = updates if updates is not None else [UPDATE]
        self.callback = callback

    def generate(self, role, system, payload):
        self.calls.append((role, copy.deepcopy(payload)))
        if 'approved_event' in payload:
            if self.callback:
                self.callback('continuity')
            return json.dumps({'updates': self.updates})
        if role == 'gm':
            return RESPONSE
        if self.callback:
            self.callback('audit')
        return json.dumps(next(self.reviews))


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'campaign'
        self.profile = self.root / 'Characters/Mira.txt'
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text('Mira is in the tower.', encoding='utf-8')
        (self.root / 'Rules.txt').write_text('Never invent dice results.', encoding='utf-8')
        self.store = Store(self.root)
        self.first = self.store.snapshot()
        self.continuity = self.root / 'Continuity/Characters/Mira.txt'

    def play(self, reviews=(APPROVE,), **kwargs):
        return Engine(self.store, FakeModel(reviews, **kwargs)).play('Speak to Mira')

    def test_discovery_profile_continuity_and_original_backups(self):
        self.assertTrue(self.continuity.exists())
        self.assertEqual(len(self.first['continuity_targets']), 1)
        original = self.profile.read_bytes()
        self.profile.write_text('Mira is now in the yard.', encoding='utf-8')
        state = self.store.snapshot()
        self.assertNotEqual(state['revision'], self.first['revision'])
        self.assertEqual(state['documents']['Characters/Mira.txt']['content'], 'Mira is now in the yard.')
        self.assertEqual((self.store.meta / 'history' / (digest(original) + '.txt')).read_bytes(), original)
        self.assertEqual(self.store.snapshot()['revision'], state['revision'])

    def test_only_explicit_profiles_receive_continuity(self):
        result = self.play(updates=[])
        self.assertEqual(result['status'], 'approved')
        self.assertEqual(list(self.continuity.parent.glob('*.txt')), [self.continuity])
        (self.root / 'world.txt').write_text('An incidental guard called Jon exists.', encoding='utf-8')
        self.store.snapshot()
        self.assertFalse((self.continuity.parent / 'Jon.txt').exists())
        (self.profile.parent / 'Jon.txt').write_text('Jon is cautious.', encoding='utf-8')
        self.store.snapshot()
        self.assertTrue((self.continuity.parent / 'Jon.txt').exists())
        self.profile.unlink()
        state = self.store.snapshot()
        self.assertNotIn('Continuity/Characters/Mira.txt', state['documents'])
        self.assertTrue(self.continuity.exists())
        self.assertTrue(state['warnings'])

    def test_three_rejections_pause_without_canon_or_file_changes(self):
        before = self.continuity.read_bytes()
        model = FakeModel([REJECT] * 3)
        result = Engine(self.store, model).play('Find Mira')
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(len(result['audit']), 3)
        self.assertFalse(any('approved_event' in p for _, p in model.calls))
        self.assertEqual(self.continuity.read_bytes(), before)
        self.assertEqual(self.first['revision'], self.store.snapshot()['revision'])
        with self.assertRaises(ValueError):
            Engine(self.store, FakeModel()).play('Wait')
        self.store.resume(result['id'])
        self.assertEqual(self.play()['status'], 'approved')

    def test_approved_event_precedes_proposals_and_rejected_drafts_are_excluded(self):
        def check(phase):
            if phase == 'continuity':
                self.assertEqual(len([e for e in self.store.snapshot()['events'] if e['kind'] == 'story']), 1)
        model = FakeModel([REJECT, APPROVE], callback=check)
        result = Engine(self.store, model).play('Talk')
        self.assertEqual(result['status'], 'approved')
        self.assertEqual(model.calls[2][1]['previous_attempts'][0]['review'], REJECT)
        self.assertNotIn('Wrong location', json.dumps(model.calls[-1][1]))
        self.assertNotIn('Wrong location', json.dumps(canonical_sources(self.store.snapshot())))

    def test_player_confirmed_updates_append_without_modifying_profile(self):
        profile, old = self.profile.read_bytes(), self.continuity.read_bytes()
        result = self.play()
        self.assertEqual(self.continuity.read_bytes(), old)
        self.store.accept_updates(result['id'])
        self.assertTrue(self.continuity.read_bytes().startswith(old))
        self.assertIn('[OBJECTIVE / promise]', self.continuity.read_text())
        self.assertEqual(self.profile.read_bytes(), profile)
        self.assertEqual((self.store.meta / 'history' / (digest(old) + '.txt')).read_bytes(), old)
        self.assertEqual(Store(self.root).turn(result['id'])['proposals'], [])
        with self.assertRaises(ValueError):
            self.store.accept_updates(result['id'])

    def test_external_edit_during_generation_prevents_canon(self):
        def edit(phase):
            if phase == 'audit':
                self.profile.write_text('Mira has left the tower.', encoding='utf-8')
        result = self.play(callback=edit)
        self.assertEqual(result['status'], 'error')
        self.assertFalse(any(e['kind'] == 'story' for e in self.store.snapshot()['events']))

    def test_external_edit_before_confirmation_preserved(self):
        result = self.play()
        self.continuity.write_text('Newer user edit.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.store.accept_updates(result['id'])
        self.assertEqual(self.continuity.read_text(), 'Newer user edit.')
        self.assertEqual(self.store.pending_updates()[0]['id'], result['id'])

    def test_race_after_scan_is_detected_at_write(self):
        result = self.play()
        original = self.store._write_changes
        def race(changes):
            self.continuity.write_text('Racing edit', encoding='utf-8')
            return original(changes)
        with patch.object(self.store, '_write_changes', side_effect=race):
            with self.assertRaises(ValueError):
                self.store.accept_updates(result['id'])
        self.assertEqual(self.continuity.read_text(), 'Racing edit')

    def test_recovery_finishes_player_approved_write_intent(self):
        result = self.play()
        with patch.object(self.store, '_write_changes', side_effect=OSError('power failure')):
            with self.assertRaises(OSError):
                self.store.accept_updates(result['id'])
        fresh = Store(self.root)
        fresh.snapshot()
        self.assertIn(RESPONSE, self.continuity.read_text())
        self.assertEqual(fresh.turn(result['id'])['proposals'], [])

    def test_recovery_never_clobbers_newer_editor_contents(self):
        result = self.play()
        with patch.object(self.store, '_write_changes', side_effect=OSError('power failure')):
            with self.assertRaises(OSError):
                self.store.accept_updates(result['id'])
        self.continuity.write_text('User saved after crash.', encoding='utf-8')
        Store(self.root).snapshot()
        self.assertEqual(self.continuity.read_text(), 'User saved after crash.')

    def test_invalid_audit_or_proposals_fail_closed(self):
        invalid = copy.deepcopy(REJECT)
        invalid['issues'][0]['quote'] = 'invented'
        self.assertEqual(self.play([invalid])['status'], 'error')
        invalid_update = copy.deepcopy(UPDATE)
        invalid_update['document'] = 'Characters/Mira.txt'
        result = self.play(updates=[invalid_update])
        self.assertEqual(result['status'], 'approved')
        self.assertFalse(result['proposals'])
        self.assertIn('error', result['continuity_audit'][-1])
        for bad in ('Continuity/Characters/Incidental.txt', '../escape.txt', 'Rules.txt'):
            update = dict(UPDATE, document=bad)
            with self.assertRaises(ValueError):
                validate_updates(json.dumps({'updates': [update]}), self.store.snapshot(), RESPONSE)

    def test_external_invalid_json_after_story_commit_does_not_hide_approved_response(self):
        def edit(phase):
            if phase == 'continuity':
                (self.root / 'world.json').write_text('{broken', encoding='utf-8')
        result = self.play(callback=edit)
        self.assertEqual(result['status'], 'approved')
        self.assertEqual(result['response'], RESPONSE)
        self.assertEqual(result['proposals'], [])
        self.assertIn('error', result['continuity_audit'][-1])

    def test_knowledge_requires_when_and_how_and_beliefs_are_labeled(self):
        update = copy.deepcopy(UPDATE)
        entry = update['entries'][0]
        entry.update(category='knowledge', learned_how='not established')
        with self.assertRaises(ValueError):
            validate_updates(json.dumps({'updates': [update]}), self.first, RESPONSE)
        entry.update(category='relationship', perspective='suspicion')
        result = self.play(updates=[update])
        self.store.accept_updates(result['id'])
        self.assertIn('[SUSPICION / relationship]', self.continuity.read_text())

    def test_bad_json_and_deleted_files_discovered_without_import(self):
        path = self.root / 'world.json'
        path.write_text('{bad', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.snapshot()
        path.write_text('{"moon": "red"}', encoding='utf-8')
        self.assertIn('world.json', self.store.snapshot()['documents'])
        path.unlink()
        self.assertNotIn('world.json', self.store.snapshot()['documents'])

    def test_damaged_log_stops_loading(self):
        self.store.log.write_bytes(self.store.log.read_bytes() + b'{incomplete')
        with self.assertRaisesRegex(ValueError, 'Incomplete event log'):
            self.store.snapshot()

    def test_context_limit_and_path_escape(self):
        (self.root / 'large.txt').write_text('x' * 19000)
        with self.assertRaisesRegex(ValueError, 'context budget'):
            self.play()
        (self.root / 'large.txt').unlink()
        outside = Path(self.tmp.name) / 'outside.txt'
        outside.write_text('outside')
        try:
            (self.root / 'linked.txt').symlink_to(outside)
        except OSError:
            self.skipTest('symlink creation unavailable')
        with self.assertRaises(ValueError):
            self.store.snapshot()


if __name__ == '__main__':
    unittest.main()
