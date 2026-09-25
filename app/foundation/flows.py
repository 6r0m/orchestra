"""The flows a run may follow: which stages, in which order, and where the operator answers.

A flow is a file in `flows/` at the checkout root, named for the flow and holding its steps —
`role:action`, in order. The stages, and which role takes each, are the stages' contract
(`stages`); the rules a flow keeps are here, and one that breaks a rule is refused with the rule
it broke. Only a run's start reads a flow: the run is handed its steps, so a flow edited later
changes only the runs started after it, and the workflow never reads a file.
"""
import json
import os
import re

from app.foundation import paths
from app.foundation import stages

FLOWS_DIR = os.path.join(paths.REPO, "flows")
# The operator's own steps: an approval where the flow schedules one, and the final gate — the only way
# to a merge.
OPERATOR = "you"
GATES = ("approve", "merge")
# A run stays the bounded work one workflow is meant for; a flow that genuinely outgrows this is the
# evidence to revisit the limit.
MAX_FLOW_STEPS = 32
# The steps of a run started before flows existed, as that code took them. It never changes, so those
# runs replay.
LEGACY_FLOW = ("engineer:plan", "architect:assess", "you:approve",
               "engineer:build", "architect:verify", "you:merge")
# A flow's name is its file's, and never a path.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class InvalidFlow(ValueError):
    """A flow that breaks a rule, or that does not exist; nothing has run."""


def is_name(value):
    """Whether `value` can name a flow — the one grammar for a flow's name, wherever one is taken."""
    return isinstance(value, str) and _NAME.fullmatch(value) is not None


def split(step):
    role, _, action = step.partition(":")
    return role, action


def check(steps):
    """`steps`, when they keep every rule; InvalidFlow naming the first one broken."""
    if not isinstance(steps, list) or not all(isinstance(step, str) for step in steps):
        raise InvalidFlow("a flow is a list of steps, each `role:action`")
    if not 1 <= len(steps) <= MAX_FLOW_STEPS:
        raise InvalidFlow("a flow has from 1 to %d steps, not %d" % (MAX_FLOW_STEPS, len(steps)))
    judged_by = {work: review for review, work in stages.REVIEWS.items()}
    actions = [split(step)[1] for step in steps]
    planned = False
    for index, step in enumerate(steps):
        role, action = split(step)
        before = actions[index - 1] if index else None
        after = actions[index + 1] if index + 1 < len(steps) else None
        where = "step %d, %r" % (index + 1, step)
        if role == OPERATOR:
            if action not in GATES:
                raise InvalidFlow("%s: the operator's steps are %s"
                                  % (where, ", ".join("%s:%s" % (OPERATOR, gate) for gate in GATES)))
            if action == "approve" and before not in tuple(stages.REVIEWS) + stages.ANSWERS:
                raise InvalidFlow("%s: an approval follows a review or a research" % where)
            if action == "merge" and (before != "verify" or after is not None):
                raise InvalidFlow("%s: the merge is the last step, right after a verify" % where)
            continue
        if action not in stages.STAGE_ROLE:
            raise InvalidFlow("%s: no such action; the actions are %s" % (where, ", ".join(stages.STAGES)))
        if role != stages.STAGE_ROLE[action]:
            raise InvalidFlow("%s: %s is the %s's" % (where, action, stages.STAGE_ROLE[action]))
        if action in judged_by and after != judged_by[action]:
            raise InvalidFlow("%s: the %s's work goes to its review, %s, next" % (where, role, judged_by[action]))
        if action in stages.REVIEWS and before != stages.REVIEWS[action]:
            raise InvalidFlow("%s: %s judges a %s right before it" % (where, action, stages.REVIEWS[action]))
        if action == "build" and not planned:
            raise InvalidFlow("%s: a build implements a plan, and no plan comes before it" % where)
        if action in stages.ANSWERS and planned:
            raise InvalidFlow("%s: research comes before any plan, which starts from its brief" % where)
        planned = planned or action == "plan"
    if "build" in actions and actions[-1] != "merge":
        raise InvalidFlow("a flow that builds ends at the merge: `%s:merge`" % OPERATOR)
    return steps


def steps_of(flow):
    """The steps of the flow a run is handed — `{name, steps}`, as a start gives it — checked, and taken as
    given: a flow of another shape is refused, never made into one."""
    if not isinstance(flow, dict) or set(flow) != {"name", "steps"}:
        raise InvalidFlow("a run is handed its flow as {name, steps}")
    if not is_name(flow["name"]):
        raise InvalidFlow("%r is not a flow's name" % (flow["name"],))
    return check(flow["steps"])


def load(name):
    """The steps of the flow `name` in `flows/`, checked."""
    path = os.path.join(FLOWS_DIR, "%s.json" % name) if is_name(name) else None
    if path is None or not os.path.isfile(path):
        raise InvalidFlow("no flow %r in %s" % (name, FLOWS_DIR))
    try:
        with open(path, encoding="utf-8") as fh:
            steps = json.load(fh)
    except OSError as exc:
        raise InvalidFlow("flow %r could not be read: %s" % (name, exc)) from exc
    except ValueError as exc:
        raise InvalidFlow("flow %r is not JSON: %s" % (name, exc)) from exc
    try:
        return check(steps)
    except InvalidFlow as exc:
        raise InvalidFlow("flow %r: %s" % (name, exc)) from exc


def available():
    """Every flow in `flows/`, by name: its steps, or why it is refused."""
    found = []
    names = sorted(os.listdir(FLOWS_DIR)) if os.path.isdir(FLOWS_DIR) else []
    for name, extension in (os.path.splitext(file) for file in names):
        if extension != ".json":
            continue
        try:
            found.append({"name": name, "steps": load(name)})
        except InvalidFlow as exc:
            found.append({"name": name, "error": str(exc)})
    return found


def segments(steps):
    """The checked steps as a run takes them: each work step, the review that judges it and the operator's
    step after them, where the flow has them — each as its index in `steps` and its action."""
    taken = []
    for index, step in enumerate(steps):
        role, action = split(step)
        if role == OPERATOR:
            taken[-1]["gate"] = (index, action)
        elif action in stages.REVIEWS:
            taken[-1]["review"] = (index, action)
        else:
            taken.append({"work": (index, action), "review": None, "gate": None})
    return taken
