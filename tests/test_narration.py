import io
import json
import unittest
from unittest.mock import patch

import test_core as fixtures
from test_core import APPROVE
from rpg.engine import Engine, Ollama, validate_audit
from rpg.narration import replay_issue
from rpg.retrieval import Retriever

SCENE = '''### Opening Scene

The market lamps burn low beneath the old stone arch. A porter draws a cart across the
square while the last stallholders count their coins and fold their awnings. Rain gathers
on the roofs. At the guild door a messenger waits, holding a sealed report in one hand
and watching the street for anyone who might answer the council's request for help.

"Will you hear the details?" the messenger asks.'''


class NarrationTests(unittest.TestCase):
    def setUp(self):
        fixtures.CoreTests.setUp(self)
        self.seed = self.store.begin_turn('Start an adventure.', self.store.snapshot()['revision'])
        self.store.finish_turn(self.seed, 'approved', [], SCENE)

    def test_replayed_opening_is_rejected_even_if_model_audit_approves(self):
        class Model:
            count = 0
            def generate(inner, role, system, payload):
                if 'approved_event' in payload:
                    return '{"updates": []}'
                if role == 'gm':
                    inner.count += 1
                    return SCENE if inner.count == 1 else 'The messenger breaks the seal. "Two families are missing," she says.'
                return json.dumps(APPROVE)
        result = Engine(self.store, Model()).play('What does the report actually say?')
        self.assertEqual(result['status'], 'approved', result['audit'])
        self.assertEqual(len(result['audit']), 2)
        first = result['audit'][0]
        self.assertTrue(first['application_checks'])
        self.assertFalse(first['review']['approved'])
        sources = Retriever(self.store.snapshot()).full
        validate_audit(json.dumps(first['review']), sources)
        stories = [e['payload']['turn']['response'] for e in self.store.snapshot()['events'] if e['kind'] == 'story']
        self.assertEqual(stories.count(SCENE), 1)
        self.assertIn('Two families are missing', result['response'])

    def test_repeated_openings_pause_after_three_and_keep_canon_unchanged(self):
        class Model:
            def generate(inner, role, system, payload):
                return SCENE if role == 'gm' else json.dumps(APPROVE)
        before = self.store.snapshot()['revision']
        result = Engine(self.store, Model()).play('I read the report.')
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(len(result['audit']), 3)
        self.assertEqual(before, self.store.snapshot()['revision'])

    def test_explicit_recap_and_short_repeated_phrases_remain_allowed(self):
        self.assertIsNone(replay_issue(SCENE, SCENE, 'Please recap the scene.', 'event:1'))
        self.assertIsNotNone(replay_issue(SCENE, SCENE, 'I repeat my question.', 'event:1'))
        self.assertIsNone(replay_issue('The messenger waits. What do you do?', 'The messenger waits. What do you do?', 'I wait.', 'event:1'))
        self.assertIsNone(replay_issue('She replies, "Because the tracks are human."', SCENE, 'Why not a monster?', 'event:1'))

    def test_ollama_receives_actual_recent_conversation_and_final_player_input(self):
        calls = []
        class StubOpener:
            def open(inner, request, timeout):
                body = json.loads(request.data)
                calls.append(body)
                if 'format' not in body:
                    text = 'The messenger replies, "The tracks are human."'
                else:
                    payload = json.loads(body['messages'][1]['content'])
                    text = json.dumps({'updates': []}) if 'approved_event' in payload else json.dumps(APPROVE)
                return io.BytesIO(json.dumps({'done': True, 'message': {'content': text}}).encode())
        action = '"Why are you certain it is not a monster?"'
        with patch('urllib.request.build_opener', return_value=StubOpener()):
            result = Engine(self.store, Ollama()).play(action)
        self.assertEqual(result['status'], 'approved', result['audit'])
        messages = calls[0]['messages']
        self.assertEqual(messages[-3], {'role': 'user', 'content': 'Start an adventure.'})
        self.assertEqual(messages[-2], {'role': 'assistant', 'content': SCENE})
        self.assertEqual(messages[-1], {'role': 'user', 'content': action})
        reference = json.loads(messages[1]['content'].split('\n', 1)[1])
        self.assertFalse(any(k.startswith('event:') for k in reference['sources']))
        self.assertIn('player_control', reference['sources'])
