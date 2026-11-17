"""Versioned todo outcomes; completion of a run is separate from completion of its task."""
import json
import posixpath

VERSION = 1
DISPOSITIONS = ('active', 'parked', 'backlog', 'completed')
MATERIALS_ASK = '''If the verified todo has a same-stem companion folder, move its reviewed files unchanged
alongside a retained todo, preserving their exact relative layout and links; do not accidentally nest the
source folder inside a destination left by an earlier attempt. With a completed deletion policy retain
the reviewed folder in place. Do not add, rewrite or delete reviewed materials during closeout;
return to build for content changes.'''
ASK = '''Return one plain final JSON object with "todo": {"disposition": "active|parked|backlog|completed", "remaining": "outstanding work", "reason": "blocker/resumption condition or deferral reason"}.
Choose active when work remains unless operator guidance supports parking blocked work or deferring it to backlog.
Use completed only when the defined task is complete or an attributable operator decision explicitly waives
remaining criteria. Deferral is not a waiver. Completed requires an empty remaining string; other outcomes
require remaining work, and parked/backlog also require a reason. Do not invent operator authorization.
For unfinished work retain the entire verified todo unchanged: move it as a file if necessary, optionally
prepending a short status, remaining-work and resumption note. Parked/backlog files must contain the exact
reason you declare in the final product; prepend it if missing. Never shorten or rewrite original contents.
An engineering increment can finish without its original problem being solved. The operator will review
this outcome and remaining work at Merge. Include commit_message in this same object when requested.\n''' + MATERIALS_ASK


def materials_path(todo):
    """A task's same-stem companion folder, with portable Git path separators."""
    return posixpath.splitext(todo.replace('\\', '/'))[0]


def product(final):
    """Only the native final assistant product can declare an artifact outcome."""
    try:
        value = json.loads(final)['todo']
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError('closeout requires a final JSON todo product') from error
    if (not isinstance(value, dict) or set(value) != {'disposition', 'remaining', 'reason'} or
            value.get('disposition') not in DISPOSITIONS or
            any(not isinstance(value[key], str) or len(value[key].encode('utf-8')) > 16384 or
                '\x00' in value[key] for key in ('remaining', 'reason'))):
        raise ValueError('invalid todo closeout product')
    remaining, reason = value['remaining'].strip(), value['reason'].strip()
    if value['disposition'] == 'completed' and remaining:
        raise ValueError('a completed todo cannot have remaining work')
    if value['disposition'] != 'completed' and not remaining:
        raise ValueError('unfinished todo requires remaining work')
    if value['disposition'] in ('parked', 'backlog') and not reason:
        raise ValueError('parked/backlog todo requires a blocker or deferral reason')
    return dict(value, remaining=remaining, reason=reason)
