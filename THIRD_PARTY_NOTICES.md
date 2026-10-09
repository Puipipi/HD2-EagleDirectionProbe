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
* **LuaJIT FFI / Windows kernel32**, present in the game's LuaJIT environment,
  are used by the isolated terrain query module for bounded read-only memory
  copies and a validated collision query. No external Runtime or BTO installation
  is required. The addon never requests a process-write API.

## Optional native-light prototype / 可选原生投光测试

* **Helmet Headlamp 1.0.0** ([author page](https://www.nexusmods.com/helldivers2/mods/16320)):
  the user explicitly authorized a temporary test using their separately installed
  `content/helmet_headlamp/runtime_mode_profiles` unit resource. The optional MOM
  switch defaults OFF. Normal guides do not require this resource. This package
  redistributes neither the resource nor its controller code. An independently
  implemented adapter creates only its own light-only helpers and changes their
  local visual light properties; existing headlamp instances/settings are untouched.
  Availability is checked before spawning. This is a prototype, not a permanent
  standalone-resource solution or a claim of compatibility with other headlamp versions.
* Native light/unit API signatures were checked against the installed reference
  and Autodesk's [Light API](https://help.autodesk.com/cloudhelp/ENU/Stingray-Help/lua_ref/obj_stingray_Light.html)
  and [Unit API](https://help.autodesk.com/cloudhelp/ENU/Stingray-Help/lua_ref/obj_stingray_Unit.html).
  Game brightness, projection direction and rendering cost remain unverified.

## Read-only reference / 只读参考

Facts used by this addon were read out of third-party material kept read-only in
the workspace. No part of any of the following is redistributed here:

* **HUD Ballistic Trajectory Overlay** - its catalog entry
  `{name="Beacon", throwable=true, offhand=true, resource_hex="16f397ca5f51f271"}`
  is the source of the beacon identity this probe enumerates, and its code is the
  reference for the `sr.World.units_by_resource` / `tostring(unit)` idioms.
  The installed BTO's seven-argument query ABI and world/preset validation are
  also evidence for `src/terrain_query.lua`, which is independently implemented.
  `terrain_contract.json` / `.lua` contain derived offsets and fingerprints of
  matching game code, not BTO source or game machine-code bytes. The audit helper
  uses private, read-only snapshots outside this repository to verify those facts.
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
