# Main view

The facts this package answers and where each reads them from. Nothing here imports another concern.

```mermaid
flowchart LR
    subgraph pkg["app/foundation"]
        paths["paths.py"]
        envpath["envpath.py"]
        policy["policy.py"]
        stages["stages.py"]
        flows["flows.py"]
    end
    settings_ext[(".orchestra/settings.json + local patch")]
    flows_ext[("flows/")]
    hostfs[("this host's disk")]
    policy -->|"the stage vocabulary"| stages
    policy -->|"the checkout root"| paths
    policy -->|"what can name a flow"| flows
    settings_ext -->|"settings data"| policy
    flows -->|"the stage contract"| stages
    flows -->|"the checkout root"| paths
    flows_ext -->|"a flow's steps"| flows
    envpath -->|"the environment root"| hostfs
```
