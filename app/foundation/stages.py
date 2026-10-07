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

STAGES = ("research", "plan", "assess", "build", "verify", "closeout")
STAGE_ROLE = {"research": "architect", "plan": "engineer", "assess": "architect",
              "build": "engineer", "verify": "architect", "closeout": "engineer"}
# Each review, and the work it judges: a review answers with a verdict on what that work left in the
# worktree. Every other stage is work — a read-only role researching included, and the closeout, which
# no review judges: the operator does, at the final gate.
REVIEWS = {"assess": "plan", "verify": "build"}
# The work whose product is its answer rather than a file: the run keeps it and hands it on.
ANSWERS = ("research",)
PHASES = ("plan", "build")            # the bounded loops: the work each review judges

# What an architect may answer, and the only words that route (D4).
VERDICTS = ("PASS", "PATCH", "BLOCKER", "UNVERIFIED")

_VERDICT_ASK = ("End your final message with exactly one JSON object and nothing after it: "
                '{"verdict": "...", "feedback": "..."}, where verdict is one '
                "of PASS, PATCH, BLOCKER, UNVERIFIED; feedback lists each "
                "required finding with evidence and the smallest safe fix, or ")
_PASS_CONFIRMATION = "is a short confirmation on PASS."
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

# What a closeout may change once the architect has passed the implementation: the repository's todo
# folders and its documentation, and nothing that `PASS` accepted as the implementation. Documentation is
# told by a file's type — the one thing every repository's files say of themselves.
CLOSEOUT_DOCUMENTS = (".md", ".mdx", ".rst", ".adoc")
# Where a closeout leaves the todo, as the repository's descriptor says its finished todos go.
CLOSEOUT_KEEPS = "This repository keeps a finished todo in {{TODO_DONE_DIR}}: move it there under its own name."
CLOSEOUT_DELETES = "This repository deletes a finished todo: delete it."


def closeout_may_change(path, folders):
    """Whether a closeout may change `path`, named as git names it: a file under one of the repository's
    todo `folders` — a done folder it does not have is None — or a document."""
    for folder in folders:
        if folder and path.startswith(folder.replace("\\", "/").strip("/") + "/"):
            return True
    return path.lower().endswith(CLOSEOUT_DOCUMENTS)


# `{{TODO_PATH}}`, `{{LOGS}}` and a closeout's `{{TODO_DONE}}` are filled in by whoever renders the ask.
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
              "Never run git commit or git push."),
    "verify": ("Independently verify the implementation in this worktree "
               "(inspect `git diff` and `git status`) against the todo at "
               "{{TODO_PATH}}.\n" + _ARCHITECT_EVIDENCE + _VERDICT_ASK + _PASS_CONFIRMATION),
    # The architect has passed the implementation, and no review follows: the operator judges this turn's
    # change at the final gate, so it changes nothing that `PASS` accepted (`closeout_may_change`). It may
    # run again after a failure or a resolved conflict, with part of it done already.
    "closeout": ("The architect passed the implementation. Close out its todo at {{TODO_PATH}}, and change "
                 "nothing else the architect verified. Whatever of this is done already stays as it is.\n"
                 "- What the todo says that stays true once this change lands belongs to the stable document "
                 "that owns it: make sure it is there, linked rather than repeated, and that no stable "
                 "document depends on the todo.\n"
                 "- Cut the todo to its record — what was decided and why, what was done, the evidence it "
                 "passed on — without working notes, superseded attempts or investigation detail.\n"
                 "- Set its status line to say that it passed, with today's date.\n"
                 "- {{TODO_DONE}}\n"
                 "Edit only the todo and documentation: a change to code, tests or configuration is refused "
                 "and stops the run. Move and delete files as files — never `git mv`, `git rm` or `git add`, "
                 "never a commit or a push: staging is the controller's."),
}
