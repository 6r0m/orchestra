# Public readiness

**Status:** Verified locally  
**Stable documentation owners:** [Using Orchestra](../docs/using.md) and [architecture](../docs/architecture/README.md)

## Goal

A new user can understand Orchestra from GitHub, start a bounded run from a clean checkout, and inspect and answer it in the Workbench. A contributor can follow each code and documentation boundary to its owner.

## Authority register

- **D1** Investigate public documentation and source ownership against the shared standards.
  - Reason: public acceptance.
- **D2** Investigate the fresh-user journey and review each live Workbench view and the organization of its styles.
  - Reason: public acceptance.
- **D3** Fix verified bugs and critical issues immediately. Leave material decisions to the operator where evidence does not choose between viable options.
  - Reason: not stated.
- **D4** Simulate the first install locally without signing in to a vendor or setting up optional services.
- **D5** Ship built-in instructions as the default and make GenosAI a public example of optional team skills.
- **D6** Use public GitHub issues for bug reports.
- **A1 [ACTIVE]** Preserve accepted workflow, permission and provider contracts while fixing failures at their owners.

## Repository and ownership investigation

- **Verified:** An anonymous HTTPS clone succeeded. GitHub's community profile identifies the README and license. It does not identify contributing, conduct, issue or pull request guidance. The [community profile checklist](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories) is a discovery aid. Its score does not establish usability or safety.
- **Verified at the baseline:** The root README repeated process layout, host containment and security contracts. Its agent diagram omitted Pi. The [README](../README.md) now introduces the product and routes to its owners. The [architecture structure](../docs/architecture/structure.md) owns the cross-component contracts.
- **Verified:** The [architecture test](../tests/test_architecture.py) enforces package imports and architecture router paths. Those checks do not judge semantic overlap or JavaScript and CSS ownership. Large modules warrant review by behavior and consumers before a split.
- **Verified:** Replay rules appeared in both the system structure and the orchestration structure. The root decision now routes to the [orchestration owner](../app/orchestration/docs/architecture/structure.md#invariants). The [Workbench browser map](../app/interfaces/workbench/static/README.md) routes to each view, shared stylesheet and renderer.
- **Inferred:** Orchestra's public differentiator is local review with native agent terminals and a human decision on the verified change. The GitHub-first comparison ties the worktree, approval and publishing lifecycle to issues and pull requests. Preserve the local workflow and describe the operator's evidence directly. [Cisco's repository agent orchestrator](https://github.com/cisco-open/repository-agent-orchestrator)

## Fresh-user and Workbench investigation

- **Verified at the baseline:** The quick start had a placeholder clone URL and omitted the skills then required by the shipped [settings](../.orchestra/settings.json). The [first-run guide](../docs/using.md#first-run) now uses the real clone and the built-in instructions. The [worker preflight](../app/application/activities.py) checks explicit bindings on the execution host.
- **Verified at the baseline:** The live demo expected a created, refused run for an invalid repository. The [start form](../app/interfaces/workbench/static/start.js) replaced the Git reason with a generic destination error. The precheck now exposes the actual refusal before sending a start.
- **Verified:** Choosing another repository left the previous destination visible because the [picker](../app/interfaces/workbench/static/picker.js) emitted a non-bubbling change event. Dedicated Chrome reproduced the missing destination request and confirmed the replacement preview after the fix.
- **Verified at the baseline:** Dedicated Chrome rendered New run, Worktrees, Settings and the stack controls at 1440, 375 and 320 CSS pixels. With populated run lists at 320 pixels the primary view started approximately 1,250 pixels down the page.
- **Verified after the change:** A narrow screen starts with the run list collapsed and the active view in the first viewport. Enter toggles the list. The final gate, file viewer and separate recorded terminal history rendered at all three widths. Reflow and operability were the criteria for the narrow layout. [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- **Verified:** A short task hides its expansion button. The demo previously selected that hidden button and calculated its distance from the pinned controls without checking focus. Dedicated Chrome confirmed the corrected probe focuses a visible control and clears the pinned controls at 1600, 1280, 600 and 320 CSS pixels.

## Decision and invariants

The Workbench start form owns its preview and error feedback. Keep the existing worker probe and run admission. Preserve the Git error in the form and refusal dialog and retain the task and name for correction. The demo must prove that this refusal sends no start request.

Use the existing settings, host validation and deployment entry points for onboarding. The shipped policy leaves stage bindings empty, so the role and stage contracts supply instructions. Teams opt into [stage skills](../docs/using.md#optional-team-skills) through the existing local settings. The documented first run should reach its human gates in a disposable local repository. Keep Temporal ownership and replay, vendor permissions and hook trust, and Git's final authorization intact.

## Implementation and verification

- [x] Reproduce lost refusal details at HTTP and browser-module boundaries. Verify the original reason, zero run requests and recovery that retains the draft.
- [x] Put the clone-to-first-run sequence in [Using Orchestra](../docs/using.md). Remove copied architecture and operating instructions in the root README. Run the documented fixture commands in the public clone.
- [x] Review documentation links and explicit component ownership. Consolidate Workbench dialog styles and repository-read error translation at their existing owners.
- [x] Recheck the live views at desktop and phone widths. Run both host suites. Finish the small Codex fixture through plan approval, independent build verification, closeout and the local Merge gate.

## Verification limits

- The local install simulation starts with Windows, WSL, systemd, Docker and uv available. Installing those prerequisites on a blank machine and signing in to a vendor are outside the simulation.

## Review record

### 2026-11-25 - Baseline

- Windows host suite passed 773 tests and WSL passed 1,006 tests. The public check passed, including the scanner's known-bad control.
- `make demo` reproduced the invalid-repository problem before a start was sent. The demo removed its worker and fixture.

### 2026-11-25 - Candidate

- The HTTP regression reproduced `502 Workflow execution failed` on target Git refusal. The browser-module regression reproduced the replacement of the original reason with a generic destination prompt. Both pass after the fix.
- The Windows host suite passed 773 tests and the WSL suite passed 1,007 tests. The focused Windows checks also exercise the target-worker HTTP regression, which is outside the default Windows suite selection.
- The anonymous checkout restored on both hosts. Its isolated Workbench opened New run and persisted the Codex-only role and skill settings across reload. A separate focused browser and architecture run passed 69 tests on each host.
- The real Codex fixture reached both PASS verdicts and landed the exact greeting and completed todo on its local branch. Git confirmed the run worktree was removed and the fixture had no remote.
- The relative-link audit resolved all 948 references. An exact-copy scan of first-party Python, JavaScript and CSS under `app/` found no repeated ten-line windows of 210 characters or more. At six lines, one match identified exception translation shared by two workflow updates in the same application client. Their commands and requests have distinct contracts. The architecture import checks and targeted owner review provide the evidence for the changed boundaries.
- `make demo` passed end to end with seven scripted runs in the live Workbench. It verified a start refusal without creating a run, revision, approval with a note, build verification, closeout, local Merge, terminal focus and replay, Stop, Force terminate, worker recovery, Discard, Remove, Pause and Reject. Temporal, Git and the Workbench confirmed the demo's cleanup.
- `make public-check` passed with its known-bad control. The same pinned scanner found no leaks in the new untracked files.

### 2026-11-25 - Local install simulation

- A disposable checkout started without local settings, repository descriptors, an environment file or a Python environment. The example environment rendered with Docker Compose. The Workbench installer created the locked WSL environment and enabled a temporary systemd user service. The simulation used a unique unit name, a spare loopback port and an empty local Temporal with the default Orchestra namespace.
- Chrome opened **New run**. Both Codex profile selections and cleared skill fields persisted across reload without vendor sign-in. A scripted settings-to-workflow test passed in WSL and five focused checks passed in a fresh Windows environment. The uninstaller removed the temporary systemd unit and closed its port.

### 2026-11-25 - Built-in defaults and optional team skills

- Both shipped flows initially refused preparation when the architect skill was absent. The new regression runs each flow's shipped policy through target preparation with no installed skills. It now passes without looking for a skill. Existing preparation tests still accept installed explicit bindings and refuse missing ones.
- The [public GenosAI example](../docs/using.md#optional-team-skills) loaded through the local settings file for both flows. Chrome verified blank defaults in a clean Workbench. The example bindings and their removal both survived reload. The focused settings, preparation and replay suite passed 50 tests.
- [Contributing](../CONTRIBUTING.md) directs bug reports to public GitHub issues and asks contributors to link fixes to the issue.
- The full Windows and WSL suites passed 774 and 1,008 tests. The public scan and relative-link audit passed.
