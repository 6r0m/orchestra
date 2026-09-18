"""Which stop a verdict asks for, and where it sends the run. No dependencies.

The workflow decides every transition from these two functions and nothing else,
so a verdict routes identically wherever it is judged.
"""


def gate_reason_for(verdict, phase, rounds, limit, auto_proceed):
    """Single owner of 'which gate, if any' — routing and state both use it.

    Returns approval | blocker | exhausted | '' (no gate: proceed or loop).
    """
    if verdict == "PASS":
        if phase == "plan" and not auto_proceed:
            return "approval"
        return ""
    if verdict == "BLOCKER":
        return "blocker"
    if rounds >= limit:            # round == max_rounds -> human (frozen rule)
        return "exhausted"
    return ""


def route_label(stage, verdict, gate_reason):
    """Where this verdict sends the run — one owner for console and trace."""
    if gate_reason:
        return "human (%s)" % gate_reason
    if verdict == "PASS":
        return "build" if stage == "assess" else "READY_FOR_HUMAN"
    return "plan" if stage == "assess" else "build"
