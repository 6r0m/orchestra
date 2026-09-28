"""The settings, loaded and validated whole, and a run's policy made from them — the one entry for the
Workbench, the command line, both workers and a run's start.

`app.foundation.policy` owns the files and what every setting shares, and loads no agent's module. This
adds what each kind of agent says through its adapter: whether a profile's values are ones it takes,
whether it can run with the access its role's contract requires, and whether it takes skills.

A run is handed its policy whole at its start (`run_policy`): each role's kind, its values, its access
and its persona's text, and the skills of the stages its flow takes. It carries that copy, so nothing
applied or edited later — settings, or a persona file — reaches a run already started.

The Settings view reads the settings with their revision (`read`) and applies its changes to the local
patch (`apply`): only where the settings came from the checkout's shared file, only against the revision
it read, one Apply at a time, validated whole before anything is written, and nothing changed when it is
refused.
"""
import os
import threading

from app.agents import adapters
from app.foundation import flows
from app.foundation import paths
from app.foundation import policy as P
from app.foundation import stages

# Why a kind cannot run a role, by the access the role's contract requires.
CANNOT = {"read": "the %s only reads, and %s has no read-only mode",
          "write": "the %s writes, and %s cannot write"}
# One Apply at a time in this process, the Workbench's, from its revision's check to its write.
_APPLYING = threading.Lock()


class Stale(P.InvalidPolicy):
    """An Apply against settings that changed since they were read: nothing was written."""


class ReadOnly(P.InvalidPolicy):
    """Settings a stack of its own was named: no Apply writes them, and none writes the checkout's."""


def load(path=None, root=paths.REPO, environ=os.environ):
    """The effective settings: `path`, or the file `ORCHESTRA_SETTINGS` names, alone; else the checkout's
    shared settings with its local patch over them — refused, naming the setting, when anything in them is
    wrong."""
    settings = P.load(path, root, environ)
    check(settings)
    return settings


def read(root=paths.REPO, environ=os.environ):
    """What the Settings view shows: the effective settings and each role's persona in effect, what the
    local patch changes, the kinds of agent there are, the revision an Apply must carry, where the settings
    came from and whether an Apply may write them — or, while they do not load, why."""
    below, local = P.sources(None, root, environ)
    # Each role's contract, which no setting changes: its access, and the stages it takes.
    roles = {role: {"access": P.ROLE_ACCESS[role],
                    "stages": [stage for stage in stages.STAGES if stages.STAGE_ROLE[stage] == role]}
             for role in P.ROLES}
    shown = {"revision": P.revision(below, local), "source": P.origin(below, root), "writable": local is not None,
             "kinds": adapters.available(), "skills": adapters.skill_names(root), "roles": roles,
             "phases": list(stages.PHASES),
             "max_persona_bytes": P.MAX_PERSONA_BYTES}
    try:
        settings = load(root=root, environ=environ)
        patch = P.read_patch(local) or {}
        personas = {role: P.persona(settings, role) for role in P.ROLES}
        shared = P.read_settings(below)
    except P.InvalidPolicy as exc:
        return dict(shown, writable=False, refused={"reason": exc.reason, "pointer": exc.pointer})
    except OSError as exc:
        return dict(shown, writable=False, refused={"reason": "%s cannot be read: %s" % (below, exc), "pointer": None})
    # What the view shows as the settings, what the patch changes of them, and what lies below it — what a
    # Revert returns a setting to.
    return dict(shown, settings={key: value for key, value in settings.items() if not key.startswith("_")},
                overrides=patch, shared=shared, personas=personas)


def apply(changes, revision, root=paths.REPO, environ=os.environ):
    """Apply the Settings view's `changes` to the local patch, when the settings are still at `revision`:
    each change touches its own setting alone, the result is validated whole, and the patch is replaced in
    one step. Refused — Stale, ReadOnly or InvalidPolicy, naming the setting — nothing is written. Returns
    what `read` returns after it."""
    below, local = P.sources(None, root, environ)
    if local is None:
        raise ReadOnly("these settings are %s, which %s names: a stack of its own, which no Apply writes"
                       % (below, P.VARIABLE))
    if not isinstance(changes, list) or not changes:
        raise P.InvalidPolicy("an Apply carries the settings it changes")
    with _APPLYING:
        if P.revision(below, local) != revision:
            raise Stale("the settings changed since they were read; read them again, then apply")
        shared = P.read_settings(below)
        patch = P.edited(shared, P.read_patch(local), changes)
        check(P.validate(dict(P.merge(shared, patch), _policy_path=P.origin(below, root))))
        try:
            P.write_patch(local, patch)
        except OSError as exc:
            raise P.InvalidPolicy("%s could not be written, and is as it was: %s" % (local, exc)) from exc
    return read(root, environ)


def check(settings):
    """Refuse what the kinds say is wrong: a profile's kind that does not load, or a value it does not take;
    a role bound to a kind that cannot run with the role's access; a skill bound to a stage whose role's kind
    takes none."""
    for name, profile in settings["agents"].items():
        try:
            adapter = adapters.load(profile["kind"])
        except adapters.Refused as exc:
            raise P.InvalidPolicy(str(exc), P.pointer("agents", name, "kind")) from exc
        for key, reason in adapter.validate(profile):
            raise P.InvalidPolicy(reason, P.pointer("agents", name, key))
    for role_name in P.ROLES:
        adapter = kind_of(settings, role_name)
        access = P.ROLE_ACCESS[role_name]
        if access not in adapter.ACCESS:
            raise P.InvalidPolicy(CANNOT[access] % (role_name, adapter.NAME), P.pointer("roles", role_name, "agent"))
    for stage in settings.get("stage_skills") or {}:
        role_name = stages.STAGE_ROLE[stage]
        adapter = kind_of(settings, role_name)
        if not adapter.SKILL:
            raise P.InvalidPolicy("the %s runs %s, which takes no skill" % (role_name, adapter.NAME),
                                  P.pointer("stage_skills", stage))


def kind_of(settings, role_name):
    """The module of the kind a role of `settings` is bound to."""
    return adapters.load(settings["agents"][settings["roles"][role_name]["agent"]]["kind"])


def run_policy(settings, steps=None):
    """The policy a run is handed at its start, from checked `settings`, taking the flow of `steps` — a
    run started with none takes the one runs took before flows.

    Each role holds its profile's name and values, the access of its contract, as the role-runs read it,
    and its persona's text, read now; the skills are those of the stages the flow takes. What only the
    settings' own host can read — where they were loaded — stays behind.
    """
    taken = {flows.split(step)[1] for step in (steps or flows.LEGACY_FLOW)}
    roles = {}
    for name in P.ROLES:
        role = settings["roles"][name]
        roles[name] = dict(settings["agents"][role["agent"]], agent=role["agent"],
                           workspace_access=P.ROLE_ACCESS[name], persona=P.persona(settings, name))
    skills = {stage: skill for stage, skill in (settings.get("stage_skills") or {}).items() if stage in taken}
    policy = {key: value for key, value in settings.items()
              if not key.startswith("_") and key not in ("agents", "roles", "stage_skills")}
    # A layered old local patch may still hold max_rounds. New runs use the shared review_rounds contract;
    # histories already carrying max_rounds keep their original policy and routing.
    if "review_rounds" in policy:
        policy.pop("max_rounds", None)
    return dict(policy, roles=roles, stage_skills=skills)
