import copy
import io
import json
import unittest
from unittest.mock import patch

from rpg.engine import Engine, Ollama
from test_core import APPROVE, RESPONSE
import test_core as fixtures


class GenerationTests(unittest.TestCase):
    def setUp(self):
        fixtures.CoreTests.setUp(self)

    def run_with_responses(self, responses, operation):
        responses = iter(responses)
        calls = []
        class StubOpener:
            def open(inner, request, timeout):
                calls.append(copy.deepcopy(json.loads(request.data)))
                return io.BytesIO(json.dumps(next(responses)).encode())
        with patch('urllib.request.build_opener', return_value=StubOpener()):
            result = operation(Ollama())
        return result, calls

    def result(self, content, reason='stop', done=True):
        return {'done': done, 'done_reason': reason, 'message': {'content': content}}

    def test_truncated_gm_restarts_once_then_complete_draft_is_audited(self):
        responses = [self.result('INCOMPLETE_UNSAFE_TEXT', 'length'), self.result(RESPONSE),
                     self.result(json.dumps(APPROVE)), self.result(json.dumps({'updates': []}))]
        turn, calls = self.run_with_responses(responses, lambda model: Engine(self.store, model).play('Give me an adventure'))
        self.assertEqual(turn['status'], 'approved')
        self.assertEqual(turn['response'], RESPONSE)
        self.assertEqual([c['options']['num_predict'] for c in calls], [2048, 4096, 2048, 2048])
        self.assertNotIn('INCOMPLETE_UNSAFE_TEXT', json.dumps(self.store.snapshot()))
        self.assertEqual(calls[0]['messages'][1], calls[1]['messages'][1])
        self.assertIn('concise, complete', calls[1]['messages'][0]['content'])

    def test_repeated_truncation_is_specific_and_never_canon(self):
        responses = [self.result('UNSAFE', 'length')] * 2
        turn, calls = self.run_with_responses(responses, lambda model: Engine(self.store, model).play('Begin'))
        self.assertEqual(turn['status'], 'error')
        self.assertEqual(len(calls), 2)
        error = turn['audit'][-1]['error']
        self.assertIn('4096-token', error)
        self.assertIn('qwen2.5:7b', error)
        self.assertFalse(any(e['kind'] == 'story' for e in self.store.snapshot()['events']))

    def test_admin_truncation_retries_json_before_approval(self):
        responses = [self.result(RESPONSE), self.result('{"approved":', 'length'),
                     self.result(json.dumps(APPROVE)), self.result('{"updates": []}')]
        turn, calls = self.run_with_responses(responses, lambda model: Engine(self.store, model).play('Begin'))
        self.assertEqual(turn['status'], 'approved')
        self.assertEqual(calls[2]['format'], 'json')
        self.assertEqual(calls[2]['options']['num_predict'], 4096)

    def test_unfinished_and_empty_responses_are_not_retried_or_accepted(self):
        for response in [self.result('partial', done=False), self.result('')]:
            def check(model):
                with self.assertRaises(ValueError):
                    model.generate('gm', 'System', {'action': 'Begin'})
            _, calls = self.run_with_responses([response], check)
            self.assertEqual(len(calls), 1)
