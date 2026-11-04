import copy
import json
import tempfile
import unittest
from pathlib import Path
from rpg.campaigns import Campaigns
from rpg.engine import Engine
from rpg.store import Store
from rpg.templates import draft_profile, template_report
from test_core import FakeModel, APPROVE, UPDATE


class ProfileModel:
    def generate(self, role, system, payload):
        return '# Name\nJon\n\n# Private Interpretations\nJon suspects the baron is afraid.\n\n# Unusual detail\nCollects moths.'


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = Campaigns(Path(self.tmp.name) / 'campaigns')
        self.store = self.manager.create('My world')
        self.template = self.store.root / 'Templates/Character_Template.txt'
        self.template.write_text('# Name\n# Private Interpretations\n', encoding='utf-8')

    def test_free_template_drives_draft_then_player_creates_profile(self):
        draft = draft_profile(self.store, ProfileModel(), 'Jon', 'Templates/Character_Template.txt', 'A suspicious guard')
        self.assertFalse((self.store.root / 'Characters/Jon.txt').exists())
        self.assertFalse((self.store.root / 'Continuity/Characters/Jon.txt').exists())
        self.assertEqual(len(self.store.profile_drafts()), 1)
        self.store.accept_profile(draft['id'], draft['content'] + '\nMy own addition.')
        profile = self.store.root / 'Characters/Jon.txt'
        self.assertIn('My own addition.', profile.read_text())
        self.assertTrue((self.store.root / 'Continuity/Characters/Jon.txt').exists())
        self.assertFalse(self.store.profile_drafts())
        with self.assertRaises(ValueError):
            self.store.accept_profile(draft['id'], 'replacement')
        with self.assertRaises(ValueError):
            draft_profile(self.store, ProfileModel(), 'Jon', 'Templates/Character_Template.txt', 'replacement')

    def test_template_change_suggests_without_rewriting_profile(self):
        profile = self.store.root / 'Characters/Mira.txt'
        profile.write_text('# Name\nMira\n# Extra legitimate detail\nLikes rain.', encoding='utf-8')
        self.store.snapshot()
        original = profile.read_bytes()
        self.template.write_text('# Name\n# Private Interpretations\n# New freeform heading\n', encoding='utf-8')
        report = template_report(self.store.snapshot())
        item = report['suggestions'][0]
        self.assertIn('New freeform heading', item['optional_missing_headings'])
        self.assertTrue(item['template_changed'])
        self.assertEqual(profile.read_bytes(), original)

    def test_stale_draft_cannot_overwrite_external_profile_or_template_edit(self):
        draft = draft_profile(self.store, ProfileModel(), 'Jon', 'Templates/Character_Template.txt', 'guard')
        self.template.write_text('New template guidance', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.accept_profile(draft['id'], draft['content'])
        self.assertFalse((self.store.root / 'Characters/Jon.txt').exists())
        draft = draft_profile(self.store, ProfileModel(), 'Jon', 'Templates/Character_Template.txt', 'guard')
        profile = self.store.root / 'Characters/Jon.txt'
        profile.write_text('Hand written profile.', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store.accept_profile(draft['id'], draft['content'])
        self.assertEqual(profile.read_text(), 'Hand written profile.')

    def test_campaigns_are_isolated_and_arbitrary_sections_load(self):
        (self.store.root / 'Characters/Mira.txt').write_text('# Private Interpretations\nIndividual details.', encoding='utf-8')
        first = self.store.snapshot()
        second = self.manager.create('Another world')
        self.assertNotIn('Characters/Mira.txt', second.snapshot()['documents'])
        self.manager.select(self.store.root)
        self.assertIn('Private Interpretations', self.manager.current.snapshot()['documents']['Characters/Mira.txt']['content'])
        self.assertEqual(first['revision'], self.manager.current.snapshot()['revision'])
        for bad in ('../escape', 'CON', 'bad:name'):
            with self.assertRaises(ValueError):
                self.manager.create(bad)

    def test_edited_rules_are_in_both_role_contexts(self):
        rules = self.store.root / 'Rules.txt'
        rules.write_text('Never roll dice. Use Private Interpretations carefully.', encoding='utf-8')
        model = FakeModel([APPROVE], updates=[])
        self.assertEqual(Engine(self.store, model).play('Wait')['status'], 'approved')
        for _, payload in model.calls:
            self.assertIn('Never roll dice.', json.dumps(payload))

    def test_custom_continuity_label_is_allowed(self):
        profile = self.store.root / 'Characters/Mira.txt'
        profile.write_text('Mira is wary.', encoding='utf-8')
        update = copy.deepcopy(UPDATE)
        update['entries'][0]['category'] = 'Private Interpretations'
        update['entries'][0]['perspective'] = 'suspicion'
        result = Engine(self.store, FakeModel([APPROVE], updates=[update])).play('Wait')
        self.store.accept_updates(result['id'])
        self.assertIn('SUSPICION / Private Interpretations', (self.store.root / update['document']).read_text())
