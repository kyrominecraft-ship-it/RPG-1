"""Per-request guards for full or retrieved context; stored history is never shortened."""
import json

SOURCE_BUDGET = 64_000
REQUEST_BUDGET = 96_000
AUXILIARY_BUDGET = 90_000
CONTEXT_TOKENS = 32_768


def check_budget(payload, limit, label, documents=None):
    size = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    if size <= limit:
        return
    detail = ''
    if documents:
        largest = sorted(((len(d['content'].encode('utf-8')), n) for n, d in documents.items()), reverse=True)[:5]
        detail = ' Largest source files: ' + '; '.join(f'{name} ({count:,} bytes)' for count, name in largest) + '.'
    raise ValueError(f'{label} uses {size:,} bytes; the per-request limit is {limit:,} bytes.'
                     + detail + ' This request was not sent to the model. Keep campaign history intact; always-included rules/player profiles and retrieved evidence must fit the request budget.')
