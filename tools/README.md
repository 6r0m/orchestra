# tools/

Developer tools for this component. Nothing here runs as part of the workflow or
the test suite.

| file | what it is for |
|---|---|
| [ui_fixture.py](ui_fixture.py) | emit one complete work item — both roles, a round sent back, a lost session rehydrated, a blocker answered with guidance, the approval with its summary, a failed build attempt continued, and a final diff — to the trace UI in seconds, through the real workflow on Temporal's time-skipping test server and without calling a model, so the operator view can be judged without spending a real run |
| [trust_probe.py](trust_probe.py) | check on this host that a repository recorded by [`trust.py`](../trust.py) raises no trust dialog in a worktree of it: it makes a throwaway repository and worktree under `tmp/`, records it as a run does, starts the real CLI there, reports whether the dialog appeared — then removes the worktree, the files and the records it made. Run it per CLI after either vendor is upgraded |
| [langfuse_dashboard.py](langfuse_dashboard.py) | create or update the *Orchestration Health* dashboard through Langfuse's API, from widgets the suite checks against the trace contract |

Both write to the real Langfuse, with the keys `telemetry.py` reads from
`secrets/langfuse.env`. They are therefore **not hermetic** and deliberately not
named `test_*`, so the suite never collects them. The fixture files its rows under
the environment `fixture`, apart from real runs.

It also writes what `gdiff -s` would copy for the fixture's worktree to
`tmp/ui-fixture/<run-id>.expected.patch`, computed by running `gdiff -s`'s own
git commands on a copy rather than through `telemetry.py`, and the run and trace
ids to `tmp/ui-fixture/last.json`. A browser check can then compare what the
final diff's copy button puts on the clipboard against an independent oracle.

## A run's repository is trusted by the run, not by you

Role turns run the agents' interactive CLIs, and both stop at a trust dialog before working in a
repository they have no record of — a turn would wait there, in its terminal, until someone answered
it in the workbench. That dialog asks what the operator answered by starting a run on that repository — a
[`repos.json`](../repos.json) entry, or a path typed into the workbench, which starts runs on any
repository — so a run records the answer itself before any agent starts ([`trust.py`](../trust.py), from the `prepare`
activity, on the run's own target host): Claude's `~/.claude.json` and Codex's `~/.codex/config.toml`
gain one entry for that repository. Both CLIs resolve a run's worktree to the repository it belongs
to, so the one entry covers every later run of it on that host (measured for both CLIs on both hosts:
a fresh repository, recorded this way, raises no dialog in a worktree of it).

Neither file is rewritten: Claude's is replaced atomically with its own contents plus the entry, and
Codex's is only appended to, never with a key it already holds — two tables of one key are not valid
TOML, and an explicit `trust_level = "untrusted"` is your decision, left alone. A CLI that was running
when a record was written takes it back when it exits, from the copy it started with, so a run records
again before every turn. Writing is best effort — a record that could not be written leaves the
dialog exactly as it was, and you answer it once in the page. Nothing is recorded for a path that is
not a directory on that host, so a fake path in a test never reaches your own configuration. Trust
lets a repository's own agent configuration and hooks load, which is why it only ever covers a
repository you started a run on.

## Only orchestration role-runs can trace

The [Claude Code observability plugin](https://github.com/langfuse/Claude-Observability-Plugin)
has no setting that limits it to some sessions: enabled and configured, it
uploads every Claude Code session on the machine, including the operator's own
work in other repositories. So no user-level configuration holds a working key:

- the plugin is disabled for the user on every host that runs role-runs, WSL and Windows —
  `claude plugin disable langfuse-observability@langfuse-observability --scope user`;
- its user settings hold no key, and its credential store (`pluginSecrets` in
  `~/.claude/.credentials.json` on Linux) holds no secret. The store matters most:
  Claude Code builds a plugin's options from the settings and then lays the stored
  secrets over them, so a stored secret outranks whatever a run supplies —
  measured with a wrong secret in a run's own settings, which still uploaded while
  the store held the right one, and uploaded nothing once the store was empty.

A traced role-run switches the plugin on for itself only:
`telemetry.harness_settings` writes a settings file, passed with `--settings`
(the highest-precedence layer after managed settings), that enables the plugin
and supplies both keys and the base URL. The file is created readable by its
owner only, in a directory of its own on the machine's temporary filesystem
rather than the repository's drive, whose mount ignores file modes; nothing
secret reaches the command line; and the stage deletes both when its role-run
ends, on failure too.

Do not configure the plugin with `/plugin configure`: that stores the secret
again and re-opens tracing for every session that has the plugin enabled.

A Claude Code session that was already running while a key worked keeps the
options it loaded and goes on uploading until it ends — measured on a session
that had been open since before the change. Removing configuration does not
stop it.

The Codex plugin needs no guard of this kind. It uploads only when
`TRACE_TO_LANGFUSE` is set, and only `telemetry.upload_codex_session` sets it,
passing the keys and the host through the uploader's environment.

## The Codex plugin must support a parent trace

The architect's turns nest under their orchestration stage only when the
[Codex observability plugin](https://github.com/langfuse/codex-observability-plugin)
accepts `LANGFUSE_CODEX_TRACEPARENT`. They also arrive without empty duplicate
turns only when it finalizes just the turn that stopped. Released versions up to
0.3.0 do neither. Both are open upstream pull requests —
[#72](https://github.com/langfuse/codex-observability-plugin/pull/72) for the
parent trace and
[#71](https://github.com/langfuse/codex-observability-plugin/pull/71) for the turn
lifecycle — so until a release includes them the plugin is built from the two
combined:

```bash
git clone https://github.com/langfuse/codex-observability-plugin <dir> && cd <dir>
git checkout --detach 31a152f3872409c5762239059ed2bb422d1f86cb    # head of #72
git fetch origin pull/71/head
git merge --no-commit --no-ff 977f3befbb46eb2b392d5e5c6ecf2a820141a1c1   # head of #71
```

The merge conflicts in three places, all for one reason: both pull requests add
an option to `convertRollout`. Keep both. `parentSpanContext` and
`finalizeTurnId` both go into its options type and into the call in `index.ts`,
and the return type is #71's `Promise<string[]>`. Two of #72's tests predate #71;
make them expect the returned turn ids, and let the test file's own `convertRollout` wrapper return
what it wraps. Then:

```bash
npx -y pnpm@9.5.0 install --frozen-lockfile
npx -y pnpm@9.5.0 run lint:tsc && npx -y pnpm@9.5.0 exec vitest run
npx -y pnpm@9.5.0 run build
root=~/.cache/orchestra/codex-observability-plugin
cp -r ~/.codex/plugins/cache/codex-observability-plugin/tracing/0.3.0 "$root"
cp plugins/tracing/dist/index.mjs "$root/dist/index.mjs"
```

The build lives under the orchestration's own directory, never in Codex's plugin cache: Codex
restores that cache whenever it starts, and a build placed there is gone after the next Codex
session. Each host that runs Codex role-runs gets the same copy — on Windows,
`%LOCALAPPDATA%\orchestra\codex-observability-plugin`.

`telemetry.upload_codex_session` sends what Codex's own Stop hook sends, the id of
the turn that stopped included, and #71 finalizes only that turn. A resumed
session writes a record before its next turn starts; without the id the plugin
exports that record as an empty turn, under every later stage.

In attached mode the plugin leaves the trace's name, session, tags and metadata to
the caller. The architect's turns therefore appear in the work item's trace tree,
under their stage, but not in the session page's inline list of observations.

A build without these changes still uploads, and degrades silently: the turns
land in a correlated separate session, and empty turns reappear. `telemetry.py`
checks the installed build for both changes before each upload — the parent-trace
input, and the option `finalizeTurnId` that #71 adds — and warns once, naming what
is missing, when a plugin upgrade has replaced the build.
