"""The stages a run can take: which role runs each, what each asks for, and what a review answers.

The contract, not its delivery. `app.agents.nodes` renders an ask into a vendor prompt and
parses the reply out of it; `app.orchestration` routes on the verdict; `app.observability`
scores it. None of them owns the words, and the stage a run is in means the same thing to
all of them.

Stage asks, the set of stages and which role takes each are code (D13): each ask names the
artifact its stage produces or judges, and a new stage is a change to the workflow. The order
a run takes them in is its flow's (`flows`). What a role *is* stays configuration — its persona
file, its brain, its model — and belongs to `policy`.
"""
from app.foundation import closeout

STAGES = ("research", "plan", "assess", "build", "verify", "closeout")
STAGE_ROLE = {"research": "architect", "plan": "engineer", "assess": "architect",
              "build": "engineer", "verify": "architect", "closeout": "engineer"}
# Each review, and the work it judges: a review answers with a verdict on what that work left in the
# worktree. Every other stage is work — a read-only role researching included.
REVIEWS = {"assess": "plan", "verify": "build"}
# The work that makes a build final once its review has passed. No review judges it: the operator does, at
# the final gate, which holds the tree it leaves — so what it may change is checked instead (`activities`).
FINAL = ("closeout",)
# The work whose product is its answer rather than a file: the run keeps it and hands it on.
ANSWERS = ("research",)
PHASES = ("plan", "build")            # the bounded loops: the work each review judges

# What an architect may answer, and the only words that route (D4).
VERDICTS = ("PASS", "PATCH", "BLOCKER", "UNVERIFIED")

_VERDICT_ASK = ("End your final message with exactly one JSON object and nothing after it: "
                '{"verdict": "...", "feedback": "..."}, where verdict is one '
                "of PASS, PATCH, BLOCKER, UNVERIFIED; feedback lists each "
                "required finding with evidence and the smallest safe fix, or ")
_PASS_CONFIRMATION = ("on PASS is a concise acceptance summary covering the original operator requests, "
                      "any evidence-backed refutations, and material verification limitations. "
                      "A required unresolved request prevents PASS; an unresolved operator decision needs BLOCKER.")
# A plan's PASS stops the run for approval, and the operator approves from this
# text alone, so it is written for that decision rather than as a confirmation.
_PASS_PLAN_SUMMARY = ("on PASS is the summary a human reads before approving "
                      "implementation: at most six short lines stating the chosen "
                      "direction, the decision and why, the blast radius (what "
                      "changes and what could break), and what is reused versus "
                      "newly built.")
# The architect judges at the level of architecture — the todo, the diff, the engineer's
# own reports and the web — and leaves running tests to the engineer, whose reports carry them.
_ARCHITECT_EVIDENCE = ("Judge from the todo, the repository, `git diff`, the engineer's "
                       "reports (its final messages, in {{LOGS}}/plan-*.out and build-*.out) "
                       "and the web. Do not run tests or builds.\n")
_BUILD_MATERIALS = (
    'Before your final build handoff to the architect, identify any remaining investigation or execution. '
    'Keep the sanitized evidence, fixtures and reusable diagnostic tools needed to continue in '
    '{{TODO_MATERIALS}}/, beside the todo under the same stem, or reuse an existing tracked stable owner. '
    'Add a README index explaining the files, provenance, limitations and how to resume; link it from the todo '
    'using a file-relative link to its companion. Keep links inside that folder relative to it; identify '
    'external stable owners with explicit repository-root paths so parking cannot break the handoff. '
    'Required future material must not exist only in ignored tmp/, another '
    'checkout, a terminal session or an ephemeral worktree. Check git check-ignore --no-index and '
    'git status --short --untracked-files=all for every required file; it must be included by the controller\'s '
    'normal Git snapshot. Do not stage or force-add ignored files. If an ignore rule blocks safe retention, '
    'resolve the repository-owned placement or report the blocker before handoff. '
    'Preserve only necessary public-safe material, never credentials, private data, raw transcripts or bulk '
    'generated logs; use curated sanitized observations/extracts and synthetic fixtures. For complete work, '
    'migrate lasting tools and findings to their stable owners rather than archiving disposable scratch. '
    'Your final report must distinguish completed work from pending work and list the retained relative paths '
    'and any missing evidence. Do not claim missing or inaccessible material was retained.\n')
_VERIFY_MATERIALS = (
    'Before PASS, independently inspect the continuation material for unfinished work, including '
    '{{TODO_MATERIALS}}/ or its named stable owner. Check the actual sanitized files, README index, todo links '
    'and Git inclusion using git check-ignore --no-index and git status --short --untracked-files=all. '
    'Evidence or tools needed for the remaining task must survive Merge and worktree cleanup, not live only '
    'in tmp/ or a session. Missing required files, ignored-only evidence, unsafe public content or an '
    'unusable handoff prevents PASS; return PATCH or BLOCKER with the exact missing material or decision.\n')

# What a closeout is told of its repository's own convention (`repos`): where a finished todo goes, and
# which documents the turn may bring up to date. Both are checked once the turn ends.
CLOSEOUT_KEEPS = "Move it to {{TODO_DONE_DIR}} under its own name: that is where this repository keeps a finished todo."
CLOSEOUT_DELETES = "Delete it: this repository deletes a finished todo."
CLOSEOUT_DOCS = ("Besides the todo you may change only this repository's documents — %s — and nothing else the "
                 "architect verified.")
CLOSEOUT_NO_DOCS = "Besides the todo you may change nothing the architect verified."
FLEXIBLE_CLOSEOUT_ASK = (
    'The architect passed an engineering increment. Prepare its todo outcome at {{TODO_PATH}}.\n' +
    closeout.ASK + '\nRepository destinations (null disables parked/backlog; completed null means delete): '
    '{{TODO_LOCATIONS}}\nActive stays at {{TODO_ACTIVE}}. Other destinations retain the assigned filename. '
    'Change only the exact todo source and chosen destination, its unchanged verified companion files, '
    'plus the repository documents: {{TODO_DOCUMENTS}}. '
    'Never change another todo. Move files without git mv/rm/add; never stage, commit, merge or push.')

# `{{TODO_PATH}}`, `{{LOGS}}` and a closeout's `{{TODO_DONE}}` and `{{CLOSEOUT_DOCS}}` are filled in by whoever
# renders the ask.
STAGE_ASK = {
    "research": ("Research the task before anyone touches the code: the problem it poses, current "
                 "practice and its options on the live web, and what the repository shows as far as you "
                 "can read it. Write no file. Answer with a research brief — the direction you recommend "
                 "and why, the options you weighed, the risks — and an abstract todo: the change in "
                 "outline, which the engineer will check against the code."),
    "plan": ("Investigate the task in the "
             "current repository and write the reviewable todo to exactly: "
             "{{TODO_PATH}}\nDo not implement. Do not commit."),
    "assess": ("Independently assess the todo at {{TODO_PATH}} against the "
               "actual repository.\n" + _ARCHITECT_EVIDENCE + _VERDICT_ASK + _PASS_PLAN_SUMMARY),
    "build": ("Implement the "
              "approved todo at {{TODO_PATH}} in this worktree.\n"
              + _BUILD_MATERIALS + "Never run git commit or git push."),
    "verify": ("Independently verify the implementation in this worktree "
               "(inspect `git diff` and `git status`) against the todo at "
               "{{TODO_PATH}}.\n" + _ARCHITECT_EVIDENCE + _VERIFY_MATERIALS + _VERDICT_ASK + _PASS_CONFIRMATION),
    # What it must leave, never how: the method is the role's persona's, or a skill's the host binds to the
    # stage. It may run again — after a failure, or a change sent back — with part of it done already.
    "closeout": ("The architect passed the implementation. Close out its todo at {{TODO_PATH}}. {{TODO_DONE}} "
                 "{{CLOSEOUT_DOCS}} What is done already stays as it is.\n"
                 "Move and delete files as files — never `git mv`, `git rm` or `git add`, never a commit or a "
                 "push."),
}
