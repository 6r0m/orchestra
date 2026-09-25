"""Which stop a verdict asks for, and where it sends the run. No dependencies.

The workflow decides every transition from these two functions and nothing else,
so a verdict routes identically wherever it is judged.
"""


def gate_reason_for(verdict, gate, rounds, limit, auto_proceed):
    """Single owner of 'which gate, if any' — routing and state both use it.

    `gate` is the operator's step after this review in the run's flow — `approve`, `merge` or None;
    `auto_proceed` skips a scheduled approval and nothing else.
    Returns approval | blocker | exhausted | '' (no gate: proceed or loop).
    """
    if verdict == "PASS":
        if gate == "approve" and not auto_proceed:
            return "approval"
        return ""
    if verdict == "BLOCKER":
        return "blocker"
    if rounds >= limit:            # round == max_rounds -> human (frozen rule)
        return "exhausted"
    return ""


def route_label(verdict, gate_reason, onward, back):
    """Where this verdict sends the run — one owner for console and trace: `onward` on a PASS (the next
    work, READY_FOR_HUMAN at the final gate, or DONE), `back` — the work it judged — otherwise."""
    if gate_reason:
        return "human (%s)" % gate_reason
    return onward if verdict == "PASS" else back
