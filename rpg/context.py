"""Bounded full-source context. No source selection or silent history removal."""
import json

SOURCE_BUDGET = 48_000
REQUEST_BUDGET = 96_000
AUXILIARY_BUDGET = 64_000
CONTEXT_TOKENS = 32_768


def check_budget(payload, limit, label, documents=None):
    size = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    if size <= limit:
        return
    detail = ''
    if documents:
        largest = sorted(((len(d['content'].encode('utf-8')), n) for n, d in documents.items()), reverse=True)[:5]
        detail = ' Largest source files: ' + '; '.join(f'{name} ({count:,} bytes)' for count, name in largest) + '.'
    raise ValueError(f'{label} uses {size:,} bytes; the full-source prototype limit is {limit:,} bytes.'
                     + detail + ' No sources were discarded. Retrieval is not implemented yet; do not delete campaign history to bypass this check.')
