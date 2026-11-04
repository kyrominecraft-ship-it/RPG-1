"""Narrow, deterministic detection of copied scene openings; not semantic adjudication."""
import re
from difflib import SequenceMatcher


def replay_issue(draft, previous, action, source):
    # Deliberately requested repetition remains legal.
    if re.search(r'\b(recap|summari[sz]e|summary|remind me|restate|repeat (?:the |that |last |previous |your )?(?:scene|narration|description|response|opening))\b', action, re.I):
        return None
    def words(text):
        # Ignore generated Markdown titles while retaining offsets into the original source.
        masked = re.sub(r'(?m)^\s*#{1,6}[^\n]*', lambda m: ' ' * len(m[0]), text)
        return list(re.finditer(r"[\w]+(?:['’][\w]+)?", masked))
    new, old = words(draft), words(previous)
    matcher = SequenceMatcher(None, [m[0].casefold() for m in new], [m[0].casefold() for m in old], autojunk=False)
    for block in matcher.get_matching_blocks():
        if block.a <= 10 and block.size >= 45:
            quote = previous[old[block.b].start():old[block.b + block.size - 1].end()]
            return {'source': source, 'quote': quote,
                    'problem': 'The draft starts by copying a long passage of already-approved narration instead of continuing the current exchange.',
                    'correction': 'Start with the immediate response to the current player input. Do not replay the arrival, introduction or offer. Preserve established events and player control.'}
    return None
