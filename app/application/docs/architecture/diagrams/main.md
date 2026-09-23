# Main view

The three ways in: what Temporal asks this host to do, what a human asks of a run, and what a human asks of the stack. Everything below is composed, not reimplemented.

```mermaid
flowchart LR
    subgraph pkg["app/application"]
        activities["activities.py"]
        client["client.py"]
        stack["stack.py"]
    end
    temporal_ext[("Temporal server")]
    concerns_ext[("agents · workspace · observability")]
    scripts_ext[("workers.sh · workers.ps1")]
    activities -->|"each concern's own contract"| concerns_ext
    client -->|"start, Update, cancel, terminate, status query"| temporal_ext
    stack -->|"who polls each queue"| client
    stack -->|"one part's start, stop, status, sweep"| scripts_ext
    temporal_ext -->|"an activity on this host's queue"| activities
```
