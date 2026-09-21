# Stops

Every stop a run can reach, and what each answer does to it. What a verdict means is
[the architect's own file](../../../roles/architect.md); which process decides a transition is
[the processes view](processes.md).

```mermaid
graph TD
    start([start]) --> prepare[resolve repository on target] -->|refused| refused([REFUSED])
    prepare --> worktree[create worktree] --> plan
    plan --> assess
    assess -. PATCH / UNVERIFIED .-> plan
    assess -. "PASS, no approval" .-> build
    assess -. "approval · blocker · exhausted" .-> stop1{{stop}}
    stop1 -. approve .-> build
    stop1 -. "revise · guide" .-> plan
    stop1 -. abort .-> aborted([ABORTED])
    build --> verify
    verify -. PATCH / UNVERIFIED .-> build
    verify -. "blocker · exhausted" .-> stop2{{stop}}
    stop2 -. guide .-> build
    stop2 -. abort .-> aborted
    verify -. PASS .-> final{{final gate · READY_FOR_HUMAN}}
    final -. "revise engineer" .-> build
    final -. "revise architect" .-> verify
    final -. "merge: conflict" .-> build
    final -. "merge" .-> merged([MERGED])
    final -. "discard, confirmed" .-> discarded([DISCARDED])
```

Any stage, the worktree's creation, a merge or a discard that fails stops at a `failed` stop, whose
`continue` runs that step once more and whose `abort` ends the run.
