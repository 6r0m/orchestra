"""The four stages of a run: which role runs each, what each asks for, and what a review answers.

The contract, not its delivery. `app.agents.nodes` renders an ask into a vendor prompt and
parses the reply out of it; `app.orchestration` routes on the verdict; `app.observability`
scores it. None of them owns the words, and the stage a run is in means the same thing to
all of them.

Stage asks and the set of stages are code, never configuration (D13): each ask names the
artifact its stage produces or judges, and a new stage is a change to the workflow. What a
role *is* stays configuration — its persona file, its brain, its model — and belongs to
`policy`.
"""

STAGES = ("plan", "assess", "build", "verify")
STAGE_ROLE = {"plan": "engineer", "assess": "architect",
              "build": "engineer", "verify": "architect"}
PHASES = ("plan", "build")            # the two bounded loops

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

# `{{TODO_PATH}}` and `{{LOGS}}` are filled in by whoever renders the ask.
STAGE_ASK = {
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
}
