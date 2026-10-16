# Eagle multi-guide performance experiment

Date: 2026-10-16. This is an offline LuaJIT harness result, not an in-game performance claim.

## Source and workspace provenance

- The task repo is `C:/Users/23825/Desktop/2-apex-x20/mods/eagle-direction-probe`, branch `main`, HEAD `668c7bebb559d4854a5fdb9214a8f85d11ef8803`.
- All task-relative paths below refer to `workspace/eagle-direction-probe/work/eagle-multi-perf-20261016/` inside the handoff ZIP. The frozen source inventory is at `workspace/eagle-direction-probe/work/eagle-multi-perf-20261016/source-inventory.json`; raw run JSON files are in that same archived task directory. They are intentionally not duplicated in this small GitHub browseable summary.
- The shared mod checkout was already dirty. This work stayed in the task's `baseline/` and `candidate/` copies and did not modify the shared production `src/` or package `dist/`. See `source-inventory.json` for the frozen snapshot inventory; this report does not restate a potentially stale Git status.
- Frozen baseline and candidate source copies are `baseline/` and `candidate/` under this task directory. Candidate benchmark source is the task copy, not dirty root `src/`.
- Main-file provenance: frozen 1.10.0 baseline `7562c947f525d915e3f1a0198556e736b56a0f76508a522a986cbb2e3ffdf8c2`; distance/pre-cordon candidate `c3f5bc25f72b47f68f45a4d8cdba8f0f9721ed9e60651e8cf7d7fd17ae00b761`; measured cordon candidate before the version-only bump `bc9e5ca4980f89ab5e54e42f3e760c45f9958ae9fc323de4319a21ae957711d6`; final `1.10.1-beta.1` main `3aea1798dd88f20f4e567f1c7e21bdfecfd21bed88c6993f75659ecd2aae7546` (the sole source difference from measured main is the version constant). The current candidate renderer is the frozen `6b9b5cbe144da8d907ec67e9dbb2cf4ff79ca6ba67b5f771898232699b03dbde`. The static-cache experiment hash `49fb2bc41385eda570d34172bb2ccea6bfc0a9b250fe50bbf92dcbd4e61262a0` is historical and was reverted.
- Each benchmark case wraps Lua `loadfile`, records every successfully loaded path, asserts all recorded production paths are under the requested source root, and writes SHA-256 values into that case's JSON. It observes ten loaded source paths in near cases. The fixture deliberately substitutes fake `eagle_terrain_query`, `eagle_stratagem_query`, performance clock, and local pose reader; native renderer APIs are fake, and the candidate renderer module itself is loaded. Thus it does not exercise live native, GPU, or all 15 package files as production modules.

## Historical static renderer cache experiment (withdrawn)

This experiment cached the number of static face slots after a successful submit to skip a repeated static scan when world, palette revision, and static batch identity were unchanged. It was not retained: repeated all-near measurements showed no robust gain, so the final candidate uses the frozen renderer. No native coordinates or temp-arena vectors were pooled.

`python -B work/eagle-multi-perf-20261016/trace_solid_renderer.py` passes: all 61 fake-native create/update/destroy events, IDs, coordinates, colors, layers, and order exactly match frozen baseline; SHA-256 of trace `e8b86fdf1de81df3c644e206dc2c0fb44fe7d3e49a5f900d2dd5f45ce6dd9db3`. The selected eight `test_solid_renderer.py` contracts pass against both baseline and candidate, including after the candidate renderer was restored.

The N8 near workload contains 1,344 aggregate static faces and 6,496 aggregate flow faces across eight guides; this is not a one-guide count. Its flow categories are cordon text 4,320 faces, dim cordon fill 768, cordon outline 1,152, sky arrows 96, and ground arrows 160. For comparison, N1 near has 168 static and 812 flow faces. In one N8 near run, 1,000 measured frames include 143 flow-reference changes and zero static-reference changes. Fake-native-boundary totals in that N8 near run were 510,048 face updates and 2,977,696 Vector3 constructions. These counts include all guides and flow changes; they are operation counts, not native timing.

## Repeated GC-enabled timing

Runs used `python -B bench_rc27_qpc.py 1000 <source-root>` in interleaved pre/candidate order B,C,C,B,B,C. The withdrawn static-scan/distance comparison is in `baseline-gc-run1..3.json` and `candidate-gc-run1..3.json`; it does not represent the final source. The current cordon comparison is in `pre-cordon-gc-run1..3.json` and `cordon-gc-run1..3.json`. Every case uses individual Windows QPC samples around `update()`, LuaJIT enabled, and LuaJIT's default collector restarted immediately before measurement. GC and JIT trace counts are recorded per case; traces continued to grow during runs, so these are cold-to-warm windows, not steady state. The harness includes Lua-side fake-native stubs and their table allocation cost, and excludes live native/GPU work.

Historical comparison only: frozen release versus the distance candidate with the static-scan experiment enabled. This table does not describe the final candidate. Median of the three per-run statistics:

| Case | Baseline mean / p99 (ms) | Candidate mean / p99 (ms) | Candidate change, mean / p99 |
|---|---:|---:|---:|
| N1 near | 0.227 / 3.992 | 0.229 / 4.016 | +0.95% / +0.61% |
| N4 near | 0.898 / 14.267 | 0.860 / 13.944 | -4.16% / -2.26% |
| N8 near | 1.795 / 28.780 | 1.778 / 27.986 | -0.97% / -2.76% |
| N1 far | 0.225 / 3.805 | 0.007 / 0.059 | -96.91% / -98.46% |
| N4 far | 0.854 / 13.251 | 0.008 / 0.067 | -99.01% / -99.49% |
| N8 far | 1.959 / 29.787 | 0.010 / 0.073 | -99.48% / -99.76% |
| N4 mixed | 0.887 / 14.002 | 0.408 / 6.833 | -53.99% / -51.20% |
| N8 mixed | 1.791 / 28.376 | 0.875 / 14.355 | -51.13% / -49.41% |

Static-scan caching has no robust all-near gain in these noisy measurements: N8 p50 worsened 11.91%, p95 worsened 1.28%, while p99 improved 2.76%. It was removed. The far and mixed improvement in this historical comparison comes from distance culling and the corresponding reduced visible workload. This is not evidence of reaching 0.05 ms/frame.

## Cordón optimization design and implementation

In `add_cordon_panels()`, `cordon_text` reads `inner_vertices` for the inner side and `vertices` for the outer side; every other shape reads `vertices`. The final candidate creates inner coordinate arrays only for inner-facing panels and skips outer interpolation/point construction for text-only columns. Template markers record both text and non-text consumers, so any shared column or vertex retains outer coordinates. No pooling was introduced; batches and records retain their existing ownership and identity behavior.

## Cordón allocation optimization (2026-10-16)

The candidate avoids constructing outer coordinates that are consumed only by the inward-facing text surface. It also avoids three inner-coordinate arrays and the empty inner-vertex table when selecting the outer surface. Shared text/non-text vertices and columns keep their outer coordinates. The implementation does not pool Lua tables or change geometry, animation cadence, terrain sampling inputs, solid submission, or line/xray paths.

`cordon_panel_diff.py` compared the pre-optimization candidate with the current candidate across 40 cases: all eight catalog types, inner/outer sides, solid/line output, plus four radial viewer angles with real side selection and xray. Produced static/flow geometry, native triangle create/update IDs, coordinates and order, and line traces were identical. A synthetic fixture that makes a non-text face reuse a text vertex and column also produced identical outputs. In the normal fixture, terrain interpolation calls fell from 18,483 to 14,382 (-4,101; -22.2%). Test-injected accounting of removed point/table construction counted 17,648 fewer Lua table constructions across the same scenarios.

Three fresh GC-enabled runs per version, interleaved pre/candidate order, measured 1,000 individual LuaJIT QPC update samples per case. Actual loaded-file paths and SHA-256 hashes are recorded inside every case in `pre-cordon-gc-run*.json` and `cordon-gc-run*.json`; all files loaded from each requested source root. The pre-cordon main hash is `c3f5bc25f72b47f68f45a4d8cdba8f0f9721ed9e60651e8cf7d7fd17ae00b761`; measured final main before version bump is `bc9e5ca4980f89ab5e54e42f3e760c45f9958ae9fc323de4319a21ae957711d6`; the 1.10.1-beta.1 main is `3aea1798dd88f20f4e567f1c7e21bdfecfd21bed88c6993f75659ecd2aae7546`. GC remained enabled. JIT trace counts continued to grow during runs (for example, N8 near candidate growth was 59, 9, and 172), so these are cold-to-warm measurements rather than a proven steady state.

| N=8 workload | p50 pre → candidate | p99 pre → candidate | p99 change |
|---|---:|---:|---:|
| Near | 0.0304 → 0.0295 ms | 27.9973 → 20.5341 ms | -26.66% |
| Far | 0.0039 → 0.00385 ms | 0.0895 → 0.0858 ms | -4.09% |
| Mixed | 0.0245 → 0.0244 ms | 13.2630 → 10.2381 ms | -22.81% |
| Cross 80 m | 0.0273 → 0.0289 ms | 26.6289 → 17.8915 ms | -32.81% |

Near N8 mean fell 22.51%; near p50 improved only 2.96%, with mixed p50 effectively unchanged and cross p50 5.86% higher. The tail improvements are promising but vary with JIT/GC and do not establish a steady-state or real-game guarantee. QPC includes Lua fixture work; fake native calls exclude actual game native/GPU costs. The 0.05 ms/frame goal is not established for all-near multi-guide play.
