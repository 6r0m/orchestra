"""Portable final-gate message and destination shapes; no Git or workflow effects."""
import json
import re

VERSION = 1
MARKER = 'Orchestra-Merge:'
DRAFT_ASK = '''Your entire final assistant message must be one plain JSON object containing "commit_message": {"subject": "a concise factual change summary", "body": "optional details"}.
Do not wrap it in Markdown fences or add text outside the object. Put any closeout report in an additional
"closeout_summary" JSON field. Keep the commit subject at most 94 characters and body concise.
Describe the actual completed change, following repository conventions. Do not use a dated todo name,
raw operator chat, tool/model/vendor credits, Co-Authored-By or Generated with lines.
This proposes text only. Do not stage, commit, merge or push. The operator edits and approves it at Merge.'''


def messages(value):
    if not isinstance(value, dict) or set(value) != {'work', 'merge'}:
        raise ValueError('provide both work and merge commit messages')
    for text in value.values():
        if not isinstance(text, str) or not text or len(text.encode('utf-8')) > 16384:
            raise ValueError('each commit message must be nonempty and at most 16 KiB')
        subject = text.split('\n', 1)[0]
        if not subject.strip() or len(subject) > 100 or subject != subject.strip():
            raise ValueError('commit subjects must contain 1–100 characters without surrounding whitespace')
        if re.search(r'[\x00-\x09\x0b-\x1f\x7f]', text):
            raise ValueError('commit messages cannot contain control characters')
        if re.search(r'(?im)^\s*(?:co-authored-by\s*:|generated with\b|orchestra-merge\s*:)', text):
            raise ValueError('commit messages cannot contain attribution or controller recovery markers')
    return dict(value)


def draft(final):
    try:
        record = json.loads(final)
        proposal = record['commit_message']
        if not isinstance(proposal, dict) or set(proposal) - {'subject', 'body'}:
            raise ValueError('invalid commit proposal')
        subject, body = proposal['subject'], proposal.get('body', '')
        if not isinstance(subject, str) or not isinstance(body, str):
            raise ValueError('invalid commit proposal text')
        suffix = '\n\n' + body if body else ''
        return {'messages': messages({'work': subject + suffix, 'merge': 'Merge ' + subject + suffix})}
    except (ValueError, TypeError, KeyError):
        return {'unavailable': 'No valid final-assistant commit proposal; enter both messages at Merge.'}


def choice(value, state):
    if (not isinstance(value, dict) or set(value) != {'version', 'branch', 'remote', 'basis', 'tree', 'messages'} or
            type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('unsupported final Merge protocol')
    branch, remote = value['branch'], value['remote']
    if (not isinstance(branch, str) or not branch or len(branch) > 255 or branch.startswith('-') or
            remote is not None and (not isinstance(remote, str) or not remote or len(remote) > 255)):
        raise ValueError('choose an existing destination branch and optional named remote')
    if not state.get('base_tip') or not state.get('final_tree'):
        raise ValueError('this run has no independently verified final-tree landing product')
    if value['basis'] != state['base_tip'] or value['tree'] != state['final_tree']:
        raise ValueError('the verified base or final tree changed; read the final gate again')
    messages(value['messages'])
    return dict(value)
