# Eagle call types and reference footprints

**Goal:** Replace unknown labels only after an unambiguous active-record match, and
adapt reference footprints without changing the actual aircraft direction or retirement.

**Authorization:** User requested autonomous continuation until manual game testing is required.
No further design approval is needed. Work remains in this existing mod checkout.

**Design:** Use an independent read-only current-process reader, guarded by the existing
matching PE/code contract. Do not invoke game native functions or depend on Runtime.
Use two consistent snapshots and mutual one-to-one spatial association. Ambiguous calls
stay unknown. Reference geometry comes from the supplied catalog, explicitly labelled REF;
it is not a measured damage boundary. Aircraft orientation always wins over throw-anchor rules.

**Files and interfaces:**

- `src/stratagem_query.lua`: `new(api?,contract?)` and `snapshot(sr,world)` returning
  rows `{type,p,anchor}` plus status and mission identity. Validate worlds, mission,
  PE/code, pointer/count bounds, short reads and a stable table header. Lazy adapter.
- `src/stratagem_profiles.lua`: eight profiles, `bounds(type)` and
  `associate(impacts,rows,now,epoch)`. Pure Lua, no engine/native access.
- Main: 5 Hz reads only with active guides and a type/range display enabled; diagnostics,
  saved independent MOM switches, dynamic cached geometry and moving labels.
- Tests: injectable native memory, concurrency/ambiguity/reuse, pure profile semantics,
  integration bounds/labels, failure fallback and the unchanged global terrain budget.
- Build: six resources, candidate 1.10.0-rc2, unchanged native terrain resources,
  manual ZIP import; GitHub prerelease after source/package verification.

**Global constraints:** No active-guide count limit. All grids still share two collision
queries per frame / 0.5 ms soft budget. Heights stay coarse/cached. New reader uses only
bounded ReadProcessMemory calls; no live process tool or automatic deployment.
Unidentified/native failure uses the previous generic guide. Once two snapshots confirm a
type, retain it through record/query loss until strike retirement or mission/world change.
Unsupported native rows block ambiguous associations but cannot be assigned.
110mm target is unknown: direction
only, no invented impact circle. Existing true-fill toggle/fallback remains available.

## Execution

- [x] Write failing query and association tests; observe failures on missing feature.
- [x] Implement independent reader and pure profiles; pass boundary and model tests.
- [x] Write failing integration tests for names/ranges/options/budgets.
- [x] Integrate labels and reference bounds; keep original direction/lifecycle.
- [x] Run complete tests, LuaJIT/envelope gates, mocked renderer benchmark and review.
- [x] Build ZIP, compare all payloads to source/index, write checksum; prepare prerelease publication.
- [x] Prepare concrete import and mission validation instructions; stop at the user-operated game step.

Validation: 165 tests passed, all six resources passed LuaJIT/envelope gates. Package
payloads equal source and Git index; both native terrain resources equal v1.9.10.
The reviewer reproduced an unsupported-type ambiguity bug; the new RED/GREEN tests
verify its fix. A full motion-cycle regression verifies short-footprint arrow visibility.
Reviewer follow-up passed all 21 relevant tests with no remaining concrete finding.
Publication follows this verified commit; mission acceptance is still pending user testing.
