# Browser terminal caching

**Status:** DONE 2026-11-13 — browser scope closed on the operator's approval; native process reuse is excluded by the operator’s clarified goal.
**Scope:** bounded role-display retention, persistent xterm snapshots and confirmed-cursor restoration.
**Authority:** D1–D8 in the [original change register](2026-11-12_1135-warm-role-terminals.md).
**Stable documentation owners:** [interfaces](../../app/interfaces/docs/architecture/structure.md)
and [usage](../../docs/using.md).

## Delivered scope

- Retained role displays across navigation, with independent run/host/role identity and input.
- Both roles warm on selection while their panels retain the operator's open/closed choice.
- Compatible native xterm screens survive refresh and an actual isolated browser shutdown/restart.
  Restoration continues from parsed, confirmed recording cursors; original recordings remain the recovery source.
- Bounded screen/byte retention, idle eviction and confirmed-closure invalidation; observable storage
  failures and refusal of incompatible, corrupt, truncated or incomplete parser state.
- Invalidation guards after asynchronous hashing and inside the IndexedDB transaction; fresh screens
  may save lower cursors after removal. Coordination metadata exists only while saves are active.
- Current-role tail following and deliberate scrollback are preserved. No native process pool,
  paid warm-up, new workflow authority or vendor-session replacement was introduced.

## Verification record

- Initial navigation and unopened-role regressions failed on discarded/cold emulators before their
  fixes. Actual Edge acceptance then demonstrated A/B/A display reuse, isolated input and confirmed-byte reconnect.
- Persistent restoration initially failed on cursor-zero replay. The corrected real-browser fixture
  passed refresh and an isolated Edge shutdown/restart. Native continuation comparisons cover normal/alternate
  buffers, attributes, cursor, character sets, mouse modes, saved positions, geometry and subsequent output.
- Storage tests cover incomplete UTF-8/ANSI and parser callbacks, identity/compatibility refusal,
  monotonic cross-tab writes, closed-run races, screen/byte pressure, quota aborts and denied/hung storage.
- Earlier browser delivery passed 915 WSL and 688 Windows tests. Those are the recorded delivery
  baseline, not a fresh full-suite run for the later invalidation corrections.
- The delayed-hash and transaction-race regressions remain in
  [terminal_cache_probe.js](../../tests/interfaces/terminal_cache_probe.js).
- Final metadata-lifetime red evidence: the isolated real-browser regression failed because an idle
  removal retained historical screen metadata. The corrected implementation passed
  `tests.interfaces.test_review_browser`: two real Edge tests, 33.6 seconds. Cases include idle removal,
  overlapping delayed saves, the oldest save finishing last, lower-cursor recovery, early returns and failures.
- Final public-safety and diff checks passed; documentation links were checked. No new paid request
  or broad suite was needed for the invalidation corrections.

## Activation evidence and limits

- Earlier approved browser activation was observed on the live Workbench; persistent screens restored
  both roles from nonzero cursors while the same engineer turn continued. Existing workflow state and
  stop were preserved. No WSL restart or agent interruption was required.
- The latest invalidation/lifetime corrections are verified in the isolated browser environment.
  Their behavior in the operator's refreshed live browser has not been independently rechecked.
- Closure here records implementation and test acceptance of the browser scope, not a claim of a fresh
  live rollout or native process reuse. The operator subsequently clarified that native process reuse is unnecessary (D8 in the original register);
  its investigation is archived without enabling it. The final-Merge/naming plan is separate.

- A small paid flow through dedicated temporary queues independently verified both role caches on the
  actual page. After F5, engineer and architect resumed their nonzero confirmed cursors in approximately
  197 and 224 ms, receiving only 51 and 50 bytes of state rather than replaying their existing records.
  Refresh sent no terminal keystrokes. Later role switches continued streaming in the same run. After
  actual local Merge, both disposable screen snapshots were absent, while historical Git milestones
  remained visible. No native process pool, hook approval or WSL restart was involved.
