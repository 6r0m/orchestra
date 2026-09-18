"""Policy: two roles, four stages, and every v1 configuration invariant.

- Two roles (D2): engineer (write) plans and builds; architect (read-only)
  assesses and verifies — the judge of the plan verifies its execution.
- Independent-judge rule (D3): the architect must not be the same model as
  the engineer, rejected here. Independence is a property of the model that
  thinks, not of the CLI that launches it.
- max_rounds (D5): architect attempts per phase, counting from 1.
- Git authority: all-false — agents never commit or push (D11).

Identifiers are data: rebinding a brain or editing a role's prompt file is
configuration; a new stage is a graph change (D13).
"""
import json
import os
import re

from app.foundation import paths

# The deployment's own policy file. `ORCH_POLICY` names another, and a role's prompt is
# always resolved against the directory of the file actually loaded, not against this one.
POLICY_FILE = os.path.join(paths.REPO, "policy.json")

ROLES = ("engineer", "architect")
STAGES = ("plan", "assess", "build", "verify")
STAGE_ROLE = {"plan": "engineer", "assess": "architect",
              "build": "engineer", "verify": "architect"}
PHASES = ("plan", "build")            # the two bounded loops
KNOWN_BRAINS = ("claude", "codex")
# Strict schemas: an unknown key is a typo, and a typo that silently does
# nothing is the worst failure mode for a config-driven system.
ROLE_KEYS = {"brain", "workspace_access", "prompt", "model", "reasoning_effort"}
# Model and effort reach a command line, so they must be plain tokens.
PLAIN_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
TOP_KEYS = {"roles", "max_rounds", "auto_proceed", "timeout_seconds", "heartbeat_seconds",
            "targets", "target_repo", "workbench_port", "stage_skills", "_policy_path"}
REPO_KEYS = {"commit_allowed", "push_allowed", "merge_allowed"}
# Where a run's agents can execute. Each host has its own task queue, polled only by
# that host's worker, so a role never runs on the wrong OS.
TARGETS = ("wsl", "windows")
# Each host's worker serves its live terminals on its own local port; the two hosts share one
# localhost, so the ports differ.
TARGET_KEYS = {"host", "worktree_root", "terminal_port"}


class InvalidPolicy(ValueError):
    pass


def load(path=None):
    if path is None:
        path = POLICY_FILE
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    raw["_policy_path"] = os.path.abspath(path)
    return validate(raw)


def validate(raw):
    unknown = set(raw) - TOP_KEYS
    if unknown:
        raise InvalidPolicy("unknown policy keys: %s" % ", ".join(sorted(unknown)))
    # A host may lead a stage's prompt with a skill of its own — its methodology, which this
    # component does not own. Unset means the prompt says everything itself.
    skills = raw.get("stage_skills") or {}
    if not isinstance(skills, dict):
        raise InvalidPolicy("stage_skills must map a stage to the skill that leads its prompt")
    for stage, skill in skills.items():
        if stage not in STAGE_ROLE:
            raise InvalidPolicy("stage_skills: %r is not a stage (%s)"
                                % (stage, ", ".join(sorted(STAGE_ROLE))))
        if not isinstance(skill, str) or not skill.startswith("/") or not skill[1:].strip():
            raise InvalidPolicy("stage_skills[%r] must be a skill invocation such as '/review'" % stage)
    roles = raw.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        raise InvalidPolicy("roles must define exactly %s" % (ROLES,))
    for name, role in roles.items():
        unknown = set(role) - ROLE_KEYS - {"prompt_path"}
        if unknown:
            raise InvalidPolicy("role %r: unknown keys: %s"
                                % (name, ", ".join(sorted(unknown))))
        for field in ("brain", "workspace_access"):
            if not isinstance(role.get(field), str) or not role[field]:
                raise InvalidPolicy("role %r needs non-empty %r" % (name, field))
        if role["brain"] not in KNOWN_BRAINS:
            raise InvalidPolicy("role %r: unknown brain %r" % (name, role["brain"]))
        for field in ("model", "reasoning_effort"):
            if field in role and not (isinstance(role[field], str)
                                      and PLAIN_TOKEN.fullmatch(role[field])):
                raise InvalidPolicy("role %r: %s must be a plain token" % (name, field))
    # A role's judging identity is (brain, model): `claude` running Opus and
    # `claude` running Fable are two different models, and the CLI they share
    # is only how they are launched. An absent model means the provider
    # default, so two roles that both omit it are the same model.
    def identity(role):
        return (role["brain"], role.get("model"))

    if identity(roles["architect"]) == identity(roles["engineer"]):
        raise InvalidPolicy(
            "D3: architect and engineer are the same model %s — the judge must "
            "not be the builder. Give them different brains, or different "
            "models on the same brain." % (identity(roles["architect"]),))
    if roles["architect"]["workspace_access"] != "read":
        raise InvalidPolicy("architect must be read-only (D3)")
    if roles["engineer"]["workspace_access"] != "write":
        raise InvalidPolicy("engineer must have write access")

    base = os.path.dirname(os.path.abspath(raw.get("_policy_path", POLICY_FILE)))
    for name, role in roles.items():
        if not isinstance(role.get("prompt"), str) or not role["prompt"]:
            raise InvalidPolicy("role %r needs a prompt file link" % name)
        role["prompt_path"] = os.path.join(base, role["prompt"])
        if not os.path.isfile(role["prompt_path"]):
            raise InvalidPolicy("role %r: prompt file missing: %s"
                                % (name, role["prompt_path"]))

    rounds = raw.get("max_rounds")
    if not isinstance(rounds, dict) or set(rounds) != set(PHASES):
        raise InvalidPolicy("max_rounds must define exactly %s" % (PHASES,))
    for phase, n in rounds.items():
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise InvalidPolicy("max_rounds.%s must be an int >= 1" % phase)

    repo = raw.get("target_repo")
    if not isinstance(repo, dict):
        raise InvalidPolicy("target_repo required")
    unknown = set(repo) - REPO_KEYS
    if unknown:
        raise InvalidPolicy("target_repo: unknown keys: %s" % ", ".join(sorted(unknown)))
    for key in ("commit_allowed", "push_allowed", "merge_allowed"):
        if repo.get(key) is not False:
            raise InvalidPolicy(
                "target_repo.%s must be false — agents never commit or push (D11)" % key)
    timeout = raw.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        raise InvalidPolicy("timeout_seconds must be an int >= 1")
    if not isinstance(raw.get("auto_proceed"), bool):
        raise InvalidPolicy("auto_proceed must be a boolean")
    heartbeat = raw.get("heartbeat_seconds")
    if not isinstance(heartbeat, int) or isinstance(heartbeat, bool) or heartbeat < 1:
        raise InvalidPolicy("heartbeat_seconds must be an int >= 1")
    targets = raw.get("targets")
    if not isinstance(targets, dict) or set(targets) != set(TARGETS):
        raise InvalidPolicy("targets must define exactly %s" % (TARGETS,))
    for name, target in targets.items():
        if not isinstance(target, dict) or set(target) != TARGET_KEYS:
            raise InvalidPolicy("targets.%s must define exactly %s" % (name, sorted(TARGET_KEYS)))
        if not (isinstance(target["host"], str) and PLAIN_TOKEN.fullmatch(target["host"])):
            raise InvalidPolicy("targets.%s.host must be a plain token" % name)
        if not (isinstance(target["worktree_root"], str) and target["worktree_root"]):
            raise InvalidPolicy("targets.%s.worktree_root must be a path" % name)
    ports = [raw.get("workbench_port")] + [target["terminal_port"] for target in targets.values()]
    for port in ports:
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            raise InvalidPolicy("workbench_port and every targets.*.terminal_port must be a port number")
    if len(set(ports)) != len(ports):
        raise InvalidPolicy("workbench_port and the terminal ports must all differ")
    return raw


def queue(policy, target):
    """The task queue of one target host: `target:<os>:<host>`."""
    return "target:%s:%s" % (target, policy["targets"][target]["host"])
