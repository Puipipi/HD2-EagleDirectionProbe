# Offline-only static `text_3d` prototype

This directory contains an isolated Lua module and a fake-engine contract test. It is not imported by the Eagle mod, packaged, or intended to run in game yet.

`native_text_static_prototype.lua` is inert when loaded. A caller must explicitly invoke:

```lua
local object, reason, cleanup = Prototype.create(stingray, world, {10, 20, 30}, ttl_seconds,
    'core/performance_hud/debug', monotonic_now, resource_available)
```

The position is a three-element array `{x, y, z}`. The required `resource_available(kind, path)` predicate must return boolean `true` for both `('font', 'core/performance_hud/debug')` and `('material', 'core/performance_hud/debug')`. Missing, false, or throwing checks fail closed before GUI creation. The module does not implement resource loading or presume an engine resource-query API.

Only the audited matching logical resource pair is accepted: font and material both use `core/performance_hud/debug` with no extension. The successful call creates one independent WorldGUI, calls `Gui.material(gui, 'core/performance_hud/debug')`, then creates one fixed static text object (`EAGLE FONT`, size 1.0; TTL is limited to 10 seconds) using the explicit font-material resource string. It constructs the GUI and text poses with separate `Matrix4x4.identity()` values and position with the engine's callable `Vector3` value. It omits Color. There are no text update/destroy calls and the text ID is not retained or reused. The returned controller exposes `tick(now, current_world)` and `cancel()`; TTL expiration, explicit cancellation, or a world change releases the whole GUI with `World.destroy_gui` when the original world is still live. If setup fails after GUI creation and cleanup also fails, `create` returns `nil, reason, cleanup_controller`; the caller must retain that third value and retry with its `tick` or `cancel`. Unknown world enumeration also preserves the handle until cleanup can be confirmed.

The fake native text boundary copies the 16-float pose and 3-float position synchronously, then advances its simulated temp-arena epoch. The test verifies call order/arguments and that controller state does not retain those temporary values, plus API failures, timeout, cancellation, and world loss. These tests verify the Lua module's boundary behavior only; they do not prove that the game accepts the call or how the text looks, occludes, or performs.

Run from the repository root:

```powershell
python -B mods/eagle-direction-probe/work/eagle-multi-perf-20261016/native-text-static-prototype/test_native_text_static_prototype.py
```
