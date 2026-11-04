"""Local lexical passage retrieval. Original files and canon are never rewritten."""
import json
import math
import re
from collections import Counter
from pathlib import PurePosixPath

from .context import SOURCE_BUDGET, check_budget

AUDIT_BUDGET = 76_000
STOP = set('the a an of to and or in on at for with is it i my me you your this that be are was were from as by'.split())
TOPICS = {
    'combat': 'combat attack fight strike sword wound injury armor defence defend dodge damage initiative weapon ambush battle',
    'relationship': 'relationship trust distrust promise persuade bargain love hate friend enemy romance jealousy loyalty lie secret social speak talk ask convince forgive betray',
    'knowledge': 'knowledge know learn belief suspicion assumption remember information discover investigate recognize recognise reveal secret',
    'travel': 'travel journey move walk run climb leap jump terrain location distance camp rest fatigue supplies',
    'magic': 'magic spell cast ritual curse enchanted enchantment mana supernatural sorcery',
}


def terms(text):
    return [w[:-1] if len(w) > 4 and w.endswith('s') and not w.endswith('ss') else w
            for w in re.findall(r'[^\W_]+', text.casefold()) if len(w) > 1 and w not in STOP]


def expanded_query(text):
    words = set(terms(text))
    topics = []
    for name, vocabulary in TOPICS.items():
        group = set(terms(vocabulary))
        if words & group:
            words |= group
            topics.append(name)
    return words, topics


def size(value):
    return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))


def is_pinned(name, content):
    path = PurePosixPath(name)
    words = set(terms(path.stem))
    if 'rule' in words or path.parts[0].casefold() == 'rules':
        return True
    if path.parts[0].casefold() == 'characters':
        return ('player' in words or bool(re.search(
            r'(?im)^\s*#*\s*(?:this is (?:the |a )?)?(?:player[- ]controlled character|player character)(?:[.:\s]|$)', content[:2000])))
    return False


def passages(source_id, text):
    if len(text.encode('utf-8')) <= 5000:
        yield source_id, text
        return
    # Unicode character offsets refer to exact substrings in the current source version.
    start = 0
    while start < len(text):
        end = min(start + 1400, len(text))
        if end < len(text):
            boundary = text.rfind('\n', start + 700, end)
            if boundary > start:
                end = boundary + 1
        yield f'{source_id}#chars={start}:{end}', text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - 180)


def event_text(row):
    return 'PLAYER ACTION:\n' + row['action'] + '\n\nAPPROVED GM RESPONSE:\n' + row['response']


class Retriever:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.documents = snapshot['documents']
        self.full = {'document:' + n: d['content'] for n, d in self.documents.items()}
        self.recent = []
        for event in snapshot['events']:
            if event['kind'] == 'story':
                row = event['payload']['turn']
                key = 'event:' + str(event['id'])
                self.full[key] = event_text(row)
                self.recent.append(key)
        self.pinned = {'document:' + n: d['content'] for n, d in self.documents.items() if is_pinned(n, d['content'])}
        self.catalog = [{'source': 'document:' + n, 'bytes': len(d['content'].encode('utf-8')), 'version': d['version']}
                        for n, d in self.documents.items()]
        # Small libraries retain complete-source behavior, including original source IDs.
        self.whole_fits = size(self.full) <= SOURCE_BUDGET
        self.chunks = []
        if not self.whole_fits:
            for key, text in self.full.items():
                if key in self.pinned:
                    continue
                for chunk_id, chunk in passages(key, text):
                    frequency = Counter(terms(key + ' ' + chunk))
                    self.chunks.append((chunk_id, chunk, frequency, sum(frequency.values())))
        df = Counter()
        for _, _, freq, _ in self.chunks:
            df.update(freq.keys())
        self.df = df

    def select(self, query, extra_queries=(), required=None, budget=SOURCE_BUDGET):
        if self.whole_fits:
            result = dict(self.full)
            if required:
                result.update(required)
            check_budget(result, budget, 'Retrieved context', self.documents)
            return result, self.report(result, [])
        check_budget(self.pinned, SOURCE_BUDGET - 8000, 'Always-included rules/player profiles (reserving retrieval space)', self.documents)
        result = dict(self.pinned)
        if self.recent:
            result[self.recent[-1]] = self.full[self.recent[-1]]
        if required:
            result.update(required)
        check_budget(result, budget, 'Always-included rules/player profiles and required evidence', self.documents)
        scene = self.full[self.recent[-1]][-1800:] if self.recent else ''
        words, topics = expanded_query(query + '\n' + '\n'.join(extra_queries) + '\n' + scene)
        mentions = {n for n in self.documents if set(terms(PurePosixPath(n).stem)) & words}
        ranked = []
        count = max(1, len(self.chunks))
        for index, (key, text, frequency, length) in enumerate(self.chunks):
            score = sum(math.log(1 + count / (1 + self.df[w])) * frequency[w] / (frequency[w] + .5 + length / 300)
                        for w in words if frequency[w])
            original = key.split('#chars=')[0]
            name = original.removeprefix('document:')
            if name in mentions:
                score += 5
            # Keep immediate scene context and basic identity even for terse actions.
            if original in self.recent[-1:]:
                score += 3
            if name.casefold().startswith('continuity/'):
                score += .3
            if name.casefold().startswith('characters/') and ('#chars=0:' in key or '#chars=' not in key):
                score += .5
            ranked.append((-score, index, key, text))
        for _, _, key, text in sorted(ranked):
            if key in result:
                continue
            candidate = dict(result, **{key: text})
            if size(candidate) <= budget:
                result[key] = text
        return result, self.report(result, topics)

    def report(self, sources, topics):
        return {'mode': 'full' if self.whole_fits else 'passages', 'topics': topics,
                'source_bytes': size(sources), 'library_bytes': size(self.full),
                'selected_sources': list(sources), 'catalog': self.catalog,
                'current_scene_source': self.recent[-1] if self.recent else None,
                'notice': ('All sources included.' if self.whole_fits else
                           'Partial evidence: rules/player profiles pinned; other files and story history retrieved. '
                           'Missing evidence is not proof of absence. Ask for lookup or clarification when needed.')}
