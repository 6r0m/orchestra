# Processes

Which process each part runs in, on which host, and the contract each relationship goes through.
Topology only: what a stage asks for, what a verdict means and what an answer does are in
[structure.md](../structure.md). Which package owns which module is [the main view](main.md).

```mermaid
graph LR
    operator([operator]) -- "browser, 127.0.0.1" --> workbench[app/interfaces/workbench/<br/>server.py + static/ page]
    operator -. "tests, automation" .-> cli[app/interfaces/cli.py]
    workbench -- "application/client.py" --> temporal[(Temporal server<br/>orchestration namespace)]
    cli -- "application/client.py: start · Update answer:&lt;stop-id&gt; · status query" --> temporal
    operator -- "terminal WebSocket, token + origin" --> wslterm
    ui([Temporal web UI]) -- reads --> temporal
    temporal -- "workflow tasks, orchestration queue" --> wslworker[WSL worker<br/>orchestration/workflow.py + routing.py]
    temporal -- "activities, target:wsl:host" --> wslhost[WSL worker<br/>application/activities.py]
    temporal -- "activities, target:windows:host" --> winhost[Windows worker<br/>application/activities.py]
    wslhost --- wslterm[WSL terminals<br/>agents/terminal.py]
    winhost --- winterm[Windows terminals<br/>agents/terminal.py]
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

Each host runs its own worker and polls its own task queue (D23), so a repository that must build
on Windows gets Windows agents and a Linux-only repository gets WSL agents — from one checkout.
