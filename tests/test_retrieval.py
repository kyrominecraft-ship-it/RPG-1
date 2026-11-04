import json
import unittest
from pathlib import Path

from rpg.context import SOURCE_BUDGET
from rpg.engine import Engine, validate_audit, canonical_sources
from rpg.retrieval import Retriever, size
import test_core as fixtures
from test_core import FakeModel, APPROVE, RESPONSE


class RetrievalTests(unittest.TestCase):
    # Reuse the storage fixture, without re-running the core test class's methods here.
    def setUp(self):
        fixtures.CoreTests.setUp(self)
        (self.root / 'Rules.txt').write_text('Always honour established character capabilities.\n' + 'Rule detail. ' * 1460, encoding='utf-8')
        (self.root / 'Characters/Player_Character.txt').write_text('This is the player-controlled character.\n' + 'Character background. ' * 1250, encoding='utf-8')
        world = self.root / 'World'
        world.mkdir()
        for i in range(10):
            (world / f'Archive{i:02}.txt').write_text(('Unrelated landscape description.\n' * 360), encoding='utf-8')
        (world / 'ZSecretHistory.txt').write_text(('Ancient weather observations.\n' * 300) + '\nThe Moonseal pact requires two independent witnesses.\n', encoding='utf-8')
        (world / 'Relationships.txt').write_text(('Village social customs.\n' * 300) + '\nMira forgave the scout debt after a winter bargain.\n', encoding='utf-8')
        self.large = self.store.snapshot()

    def test_large_library_is_playable_with_all_rules_and_player_profile(self):
        library_size = sum(len(d['content'].encode()) for d in self.large['documents'].values())
        self.assertGreater(library_size, 128_000)
        before = {p: p.read_bytes() for p in self.root.rglob('*.txt') if '.rpg' not in p.parts}
        model = FakeModel([APPROVE], updates=[])
        result = Engine(self.store, model).play('I bargain with Mira about the winter debt.')
        self.assertEqual(result['status'], 'approved')
        for _, payload in model.calls:
            sources = payload['sources']
            self.assertEqual(sources['document:Rules.txt'], self.large['documents']['Rules.txt']['content'])
            self.assertEqual(sources['document:Characters/Player_Character.txt'], self.large['documents']['Characters/Player_Character.txt']['content'])
            self.assertLessEqual(size(sources), 76_000)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(result['audit'][0]['gm_retrieval']['mode'], 'passages')
        self.assertIn('relationship', result['audit'][0]['gm_retrieval']['topics'])

    def test_topic_retrieval_exact_offsets_and_citation_checks(self):
        retriever = Retriever(self.large)
        sources, report = retriever.select('Mira winter debt bargain')
        self.assertIn('relationship', report['topics'])
        matches = [(k, v) for k, v in sources.items() if 'Mira forgave the scout debt' in v]
        self.assertTrue(matches)
        key, text = matches[0]
        original, offsets = key.split('#chars=')
        start, end = map(int, offsets.split(':'))
        self.assertEqual(text, self.large['documents'][original.removeprefix('document:')]['content'][start:end])
        review = {'approved': False, 'issues': [{'source': key, 'quote': 'Mira forgave the scout debt',
                  'problem': 'Debt already forgiven', 'correction': 'Respect the established bargain'}], 'updates': []}
        validate_audit(json.dumps(review), sources)
        review['issues'][0]['quote'] = 'invented quotation'
        with self.assertRaises(ValueError):
            validate_audit(json.dumps(review), sources)

    def test_admin_can_independently_lookup_missing_passages(self):
        class LookupModel(FakeModel):
            def generate(inner, role, system, payload):
                if role == 'gm' or 'approved_event' in payload:
                    return super().generate(role, system, payload)
                inner.calls.append((role, payload))
                if not any('Moonseal pact requires two independent witnesses.' in v for v in payload['sources'].values()):
                    return json.dumps({'lookup': ['Moonseal pact independent witnesses']})
                return json.dumps(APPROVE)
        model = LookupModel(updates=[])
        result = Engine(self.store, model).play('I wait quietly.')
        self.assertEqual(result['status'], 'approved', result['audit'])
        self.assertTrue(result['audit'][0]['lookups'])
        self.assertEqual(len([e for e in self.store.snapshot()['events'] if e['kind'] == 'story']), 1)

    def test_external_edit_refreshes_passages_without_old_content(self):
        name = 'World/ZSecretHistory.txt'
        path = self.root / name
        path.write_text('The Moonseal pact now requires three witnesses.', encoding='utf-8')
        sources, _ = Retriever(self.store.snapshot()).select('Moonseal witnesses')
        joined = '\n'.join(sources.values())
        self.assertIn('three witnesses', joined)
        self.assertNotIn('two independent witnesses', joined)

    def test_lookup_failure_cannot_create_canon(self):
        class BadLookup(FakeModel):
            def generate(inner, role, system, payload):
                if role == 'admin':
                    return json.dumps({'lookup': ['x' * 301]})
                return RESPONSE
        result = Engine(self.store, BadLookup()).play('Wait')
        self.assertEqual(result['status'], 'error')
        self.assertFalse(any(e['kind'] == 'story' for e in self.store.snapshot()['events']))

    def test_combat_routing_and_rejected_audits_never_enter_index(self):
        model = FakeModel([{'approved': False, 'issues': [{'problem': 'SECRET_REJECTED_MARKER',
            'source': 'document:Rules.txt', 'quote': 'Always honour established character capabilities.',
            'correction': 'Respect rules'}], 'updates': []}] * 3)
        self.assertEqual(Engine(self.store, model).play('I attack with my sword.')['status'], 'paused')
        retriever = Retriever(self.store.snapshot())
        sources, report = retriever.select('attack sword')
        self.assertIn('combat', report['topics'])
        self.assertNotIn('SECRET_REJECTED_MARKER', json.dumps(retriever.full))
        self.assertNotIn('SECRET_REJECTED_MARKER', json.dumps(sources))

    def test_independent_lookup_correction_reaches_gm_revision(self):
        marker = 'The Moonseal pact requires two independent witnesses.'
        class CorrectingModel(FakeModel):
            rejected = False
            def generate(inner, role, system, payload):
                if role == 'gm' or 'approved_event' in payload:
                    return super().generate(role, system, payload)
                inner.calls.append((role, payload))
                match = next((k for k, v in payload['sources'].items() if marker in v), None)
                if not match:
                    return json.dumps({'lookup': ['Moonseal pact independent witnesses']})
                if not inner.rejected:
                    inner.rejected = True
                    return json.dumps({'approved': False, 'issues': [{'source': match, 'quote': marker,
                        'problem': 'Missing witnesses', 'correction': 'Ask about the required witnesses'}], 'updates': []})
                return json.dumps(APPROVE)
        model = CorrectingModel(updates=[])
        result = Engine(self.store, model).play('I wait quietly.')
        self.assertEqual(result['status'], 'approved', result['audit'])
        self.assertEqual(len(result['audit']), 2)
        gm_calls = [p for role, p in model.calls if role == 'gm']
        self.assertTrue(any(marker in text for text in gm_calls[1]['sources'].values()))

    def test_npc_mentioning_player_is_not_misidentified_as_player_profile(self):
        from rpg.retrieval import is_pinned
        self.assertFalse(is_pinned('Characters/Mira.txt', 'Mira knows the player character.'))
        self.assertTrue(is_pinned('Characters/Arden.txt', 'This is the player-controlled character.'))

    def test_large_campaign_fits_actual_ollama_request_envelopes(self):
        import io
        from unittest.mock import patch
        from rpg.engine import Ollama
        from rpg.context import REQUEST_BUDGET
        calls = []
        class StubOpener:
            def open(inner, request, timeout):
                body = json.loads(request.data)
                calls.append(body)
                self.assertLessEqual(len(json.dumps(body, ensure_ascii=False).encode()), REQUEST_BUDGET)
                payload = json.loads(body['messages'][1]['content']) if 'format' in body else {}
                content = (json.dumps({'updates': []}) if 'approved_event' in payload else
                           json.dumps(APPROVE) if 'format' in body else RESPONSE)
                return io.BytesIO(json.dumps({'done': True, 'message': {'content': content}}).encode())
        with patch('urllib.request.build_opener', return_value=StubOpener()):
            result = Engine(self.store, Ollama()).play('I bargain with Mira about the winter debt.')
        self.assertEqual(result['status'], 'approved', result['audit'])
        self.assertFalse(any('error' in a for a in result['continuity_audit']), result['continuity_audit'])
        self.assertEqual(len(calls), 3)
