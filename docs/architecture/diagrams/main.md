# Main view

The parts of Orchestra, the service and processes they run in, and the contract each
relationship goes through. Topology only: what a stage asks for, what a verdict means and what an
answer does are in [structure.md](../structure.md).

```mermaid
graph LR
    operator([operator]) -- "browser, 127.0.0.1" --> workbench[workbench.py<br/>+ workbench/ page]
    operator -. "tests, automation" .-> cli[cli.py]
    workbench -- "client.py" --> temporal[(Temporal server<br/>orchestration namespace)]
    cli -- "client.py: start · Update answer:&lt;stop-id&gt; · status query" --> temporal
    operator -- "terminal WebSocket, token + origin" --> wslterm
    ui([Temporal web UI]) -- reads --> temporal
    temporal -- "workflow tasks, orchestration queue" --> wslworker[WSL worker<br/>workflow.py + routing.py]
    temporal -- "activities, target:wsl:host" --> wslhost[WSL worker<br/>activities.py]
    temporal -- "activities, target:windows:host" --> winhost[Windows worker<br/>activities.py]
    wslhost --- wslterm[WSL terminals<br/>terminal.py]
    winhost --- winterm[Windows terminals<br/>terminal.py]
    operator -- "terminal WebSocket, token + origin" --> winterm
    wslterm -- "argv + prompt, PTY, contained tree" --> wslagents([claude · codex on WSL])
    winterm -- "argv + prompt, ConPTY, contained tree" --> winagents([claude.exe · codex.exe])
    wslagents -. "turn hooks: events file" .-> wslterm
    winagents -. "turn hooks: events file" .-> winterm
    wslhost -- "target git: worktree, guard, merge" --> wslrepo[(WSL-target repository)]
    winhost -- "git.exe: worktree, guard, merge" --> winrepo[(Windows-target repository)]
    wslhost -. "trace rows" .-> langfuse[(Langfuse)]
    winhost -. "trace rows" .-> langfuse
    wslagents -. "turns via tracing plugin" .-> langfuse
    winagents -. "turns via tracing plugin" .-> langfuse
```

The workflow's stops, in the order a run can reach them:

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
