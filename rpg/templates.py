"""Free-text templates; heading suggestions never restrict legitimate profile content."""
import re
from .store import encoded
from .engine import canonical_sources

PROFILE_PROMPT = '''Draft ONE important NPC profile using the selected editable TXT template
as guidance and the player's brief. Use the campaign's current rules and sources. Preserve
all established character-specific information; don't make characters identical. Template
headings are suggestions, not a fixed schema. Extra legitimate details are welcome.
Return plain readable TXT only. Do not propose continuity or claim new gameplay events.
Distinguish established information from suggested new details. The result is a noncanonical
draft for player review, not a command to save a file. Never alter existing profiles.'''


def headings(text):
    result = []
    for line in text.splitlines():
        line = line.strip()
        heading = None
        if line.startswith('#'):
            heading = line.lstrip('#').strip()
        elif line.endswith(':') and len(line) < 100:
            heading = line[:-1].strip()
        if heading and heading.casefold() not in [h.casefold() for h in result]:
            result.append(heading)
    return result


def template_report(snapshot):
    docs = snapshot['documents']
    templates = {n: d for n, d in docs.items() if n.casefold().startswith('templates/') and n.lower().endswith('.txt')}
    profiles = {n: d for n, d in docs.items() if n.casefold().startswith('characters/') and n.count('/') == 1 and n.lower().endswith('.txt')}
    reports = []
    for template, doc in templates.items():
        expected = headings(doc['content'])
        for profile, p in profiles.items():
            original_template = None
            for event in snapshot['events']:
                if event['kind'] == 'sources_changed' and profile in event['payload']['documents']:
                    original_template = event['payload']['documents'].get(template)
                    break
            existing = {h.casefold() for h in headings(p['content'])}
            reports.append({'template': template, 'profile': profile,
                            'template_changed': original_template is not None and original_template != doc['version'],
                            'optional_missing_headings': [h for h in expected if h.casefold() not in existing]})
    return {'templates': list(templates), 'profiles': list(profiles), 'suggestions': reports}


def draft_profile(store, model, name, template, brief):
    name = validate_name(name)
    if not isinstance(brief, str) or not brief.strip() or len(brief) > 4000:
        raise ValueError('Enter a character brief of 1–4000 characters')
    snapshot = store.snapshot()
    if template not in template_report(snapshot)['templates']:
        raise ValueError('Choose an existing TXT file in Templates')
    target = 'Characters/' + name + '.txt'
    if any(n.casefold() == target.casefold() for n in snapshot['documents']):
        raise ValueError('A profile with this name already exists; existing profiles are never replaced')
    payload = {'name': name, 'brief': brief, 'template': snapshot['documents'][template]['content'],
               'campaign_sources': canonical_sources(snapshot)}
    if len(encoded(payload)) > 24000:
        raise ValueError('Profile drafting context exceeds the prototype budget')
    content = model.generate('gm', PROFILE_PROMPT, payload)
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 20000:
        raise ValueError('Invalid or oversized profile draft')
    return store.save_profile_draft(target, content, snapshot['revision'], template)


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[^<>:"/\\|?*\x00-\x1f]{1,80}', name) or name.endswith(('.', ' ')):
        raise ValueError('Enter a simple Windows character name without a file extension or path')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}:
        raise ValueError('This name is reserved by Windows')
    return name
