# External dependencies / 外部依赖

## Runtime / 运行期

* **Bingus Shared Loader v15+ (API 1)** - required by the addon; not
  redistributed here.
* **The game's own `stingray` scripting table** - the probe reads engine
  accessors (`Application`, `World`, `Unit`, `Vector3`, `Matrix4x4`) that the
  game exposes to Lua. These are properties of the game engine, **not** of any
  third-party runtime mod. This addon does not require, load, or declare a
  dependency on HD2Runtime or any other shared runtime package. The probe's first
  log line prints the capability table so that claim is measured, not asserted.

## Read-only reference / 只读参考

Facts used by this addon were read out of third-party material kept read-only in
the workspace. No part of any of the following is redistributed here:

* **HUD Ballistic Trajectory Overlay** - its catalog entry
  `{name="Beacon", throwable=true, offhand=true, resource_hex="16f397ca5f51f271"}`
  is the source of the beacon identity this probe enumerates, and its code is the
  reference for the `sr.World.units_by_resource` / `tostring(unit)` idioms.
* **Enemy HP** - its kill-feed table provided the GUID-to-name mapping for the
  Eagle entities (`eagle_bomb`, `eagle_base`, `eagle_gunpods`, ...).
* **homing stim**, **HD2-EXO-Stratagem-Launcher**, **Advanced-Tank-Turret**,
  **Super Laser Sights Plus** - reference for `sr.Unit.world_position`,
  `sr.Unit.world_pose`, `sr.Matrix4x4.forward`, and for the cost of walking
  `sr.World.units`.
* **HD2Runtime 0.28.1** - only as a **second-hand compilation** of entity ids and
  capability fields, consulted offline to confirm that no direction/heading field
  exists in the readable range. Its runtime payload is not used by this addon and
  contains no reference to `stingray`.

## Development / 开发期

* **Lupa / LuaJIT** (`requirements-dev.txt`) - used by the build validator's
  LuaJIT compile gate. Upstream licenses apply.
* **Bingus addon packer** - `work/standalone/build_probe.py` needs the externally
  supplied `build_addon.py` and `archive.py` in
  `work/standalone/vendor/bingus/`. Those third-party implementations are not
  redistributed in this repository (the directory is ignored on purpose);
  obtain them with the appropriate upstream permission. They encode the addon
  envelope format used by the loader.

## Not included / 不包含

This repository contains no game binaries, no other installed mods, no personal
configuration, no raw player logs and no crash dumps. The Eagle aircraft resource
path used by the probe (`content/fac_helldivers/vehicles/eagle/eagle`) was
recovered from a full process memory dump by a throwaway scanner that stays
outside this repository; the derived string list is not committed here either.

No new license grant for this project's own code is made by this snapshot.
