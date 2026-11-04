import copy
import json
import unittest

import test_core as fixtures
from test_core import APPROVE
from rpg.engine import Engine
from rpg.player_control import PLAYER_CONTROL
from rpg.retrieval import Retriever


class PlayerControlTests(unittest.TestCase):
    def setUp(self):
        fixtures.CoreTests.setUp(self)

    def seed_scene(self):
        turn = self.store.begin_turn('Start an adventure.', self.store.snapshot()['revision'])
        self.scene = 'Mira waits at the tower door. You could knock or leave. What do you do?'
        self.store.finish_turn(turn, 'approved', [], self.scene)

    def test_freeform_action_survives_rejection_and_revision_verbatim(self):
        self.seed_scene()
        action = 'I do neither. I sit on the step and ask, "Why are you guarding this tower?"'
        bad = 'You choose to knock. "Let me in," you say.'
        good = 'Mira looks at you on the step. "Because someone must," she replies. She waits for your response.'
        calls = []
        class Model:
            draft_count = 0
            def generate(inner, role, system, payload):
                calls.append((role, system, copy.deepcopy(payload)))
                if 'approved_event' in payload:
                    return '{"updates": []}'
                if role == 'gm':
                    inner.draft_count += 1
                    return bad if inner.draft_count == 1 else good
                if payload['draft'] == bad:
                    return json.dumps({'approved': False, 'issues': [{'source': 'player_control',
                        'quote': 'Do not map an unlisted action to\nits nearest suggested option, even when that seems narratively convenient.',
                        'problem': 'Invented knock and dialogue replace the actual reply.',
                        'correction': 'Keep the sitting action and exact question. Let Mira respond.'}], 'updates': []})
                return json.dumps(APPROVE)
        result = Engine(self.store, Model()).play(action)
        self.assertEqual(result['status'], 'approved', result['audit'])
        self.assertEqual(result['response'], good)
        for role, system, payload in calls:
            self.assertEqual(payload['sources']['player_control'], PLAYER_CONTROL)
            if role == 'gm':
                self.assertEqual(payload['action'], action)
                self.assertEqual(payload['sources']['player_action'], action)
            elif 'draft' in payload:
                self.assertEqual(payload['player_input'], action)
                self.assertIn('Reject invented PC speech', system)
        story = [e['payload']['turn'] for e in self.store.snapshot()['events'] if e['kind'] == 'story'][-1]
        self.assertEqual(story['action'], action)
        self.assertEqual(story['response'], good)
        self.assertNotIn(bad, json.dumps(Retriever(self.store.snapshot()).full))
        self.assertEqual(len(result['audit']), 2)

    def test_clarification_and_rule_supported_failed_attempt_are_allowed(self):
        self.seed_scene()
        for action, response in [
            ('I deal with it.', 'Do you mean the locked door or Mira?'),
            ('I try to open the locked door without a key.', 'The lock holds. The door stays closed.')]:
            class Model:
                def generate(inner, role, system, payload):
                    if 'approved_event' in payload:
                        return '{"updates": []}'
                    return response if role == 'gm' else json.dumps(APPROVE)
            result = Engine(self.store, Model()).play(action)
            self.assertEqual(result['status'], 'approved')
            self.assertEqual(result['response'], response)

    def test_three_agency_rejections_pause_and_leave_continuity_intact(self):
        self.seed_scene()
        before = self.continuity.read_bytes()
        stories_before = len([e for e in self.store.snapshot()['events'] if e['kind'] == 'story'])
        class Model:
            def generate(inner, role, system, payload):
                if role == 'gm':
                    return 'You choose to leave and swear never to return.'
                return json.dumps({'approved': False, 'issues': [{'source': 'player_control',
                    'quote': "Only the player chooses their character's voluntary actions, spoken words, intentions,\nfeelings, commitments and decisions.",
                    'problem': 'Invented a departure and promise.', 'correction': 'Respond to the actual question.'}], 'updates': []})
        result = Engine(self.store, Model()).play('I ask Mira her name.')
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(len(result['audit']), 3)
        self.assertEqual(before, self.continuity.read_bytes())
        self.assertEqual(stories_before, len([e for e in self.store.snapshot()['events'] if e['kind'] == 'story']))

    def test_latest_full_scene_is_retained_when_large_campaign_uses_retrieval(self):
        self.seed_scene()
        (self.root / 'World.txt').write_text('Unrelated lore.\n' * 7000, encoding='utf-8')
        snapshot = self.store.snapshot()
        retriever = Retriever(snapshot)
        sources, report = retriever.select('I ask a different question.')
        self.assertEqual(report['mode'], 'passages')
        self.assertEqual(sources[report['current_scene_source']], retriever.full[report['current_scene_source']])
        self.assertIn(self.scene, sources[report['current_scene_source']])
