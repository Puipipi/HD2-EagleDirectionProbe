# 1.10.0-rc10 delivery notes

This candidate fixes the rc9 native-light API gate and applies the user's calibrated Napalm reference length. It keeps the existing seven-resource package layout and GUID. The native-light option remains disabled by default.

## Native light compatibility

The persisted `EagleDirectionProbe.log` on 2026-10-09 recorded `native light unavailable: Light.set_spot_angle_start unavailable` at `11:18:47Z`. The prototype rejected the capability check before it spawned any helper, which explains why rc9 produced no red illumination. The separately installed Helmet Headlamp controller resolves lights by name and uses `Light.set_enabled`; it does not call the spot-angle, falloff, shadow, or volumetric setters removed in rc10.

Rc10 preserves the resource-authored cone, falloff and render flags. It resolves the four named functional lights and disables the handles it successfully resolves; it requires `helmet_headlamp_task_fill` to be present and red, while optional marker lights are resolved defensively. If `Unit.num_lights` exists, the prototype still checks for the expected five-light profile. `Unit.has_light` and `World.update_unit` are optional; updates are best-effort. All cleanup uses the light handles held by the prototype's own helper row.

This is an API compatibility correction, not proof of successful in-game illumination. The real optical axis, ground/rock response, brightness and GPU cost still need manual verification with the separately installed resource enabled. No Stingray blue ground-marking implementation is included or claimed as identified.

## Napalm reference calibration

The reference was 100 m long. At the user's direction, each end is shortened by `100/6` m, yielding a total length of `200/3` m (about 66.67 m). Its 20 m width, center and incoming heading remain unchanged. This is a user-calibrated display reference, not a measured damage, impact or persistent-fire boundary.

## Stingray blue ground-marking research status

Offline FileDiver v0.7.59 research resolves the Illuminate attack-ship Unit at `content/fac_illuminate/vehicles/illuminate_attack_ship/illuminate_attack_ship.unit` (name hash `19e18b46ec55d94a`, Unit type `e0a48d0be9a7453f`, archive `046d4441a6dae0a9`). Its exported model has 59 nodes, 2 meshes, 5 materials and 13 images, with no `KHR_lights_punctual` lights. The extracted aircraft state machine has no explicit effect, particle, light, decal or projector reference. These findings narrow the aircraft model/state-machine path; they do not rule out combat AI, mission logic, spawned or unnamed effects, projectiles, decals or material/terrain behavior.

The separate environment `il_spotlight_01.unit` is a useful positive control: the follow-up found a blue spot light there, but no reference connecting it to the attack ship or its ground lane. The similarly named `.particles` candidate still does not prove a ground mark. Rc10 therefore includes no Stingray blue ground-marking effect and makes no claim that the lane's source has been found. The FileDiver unit-exporter source is available at [v0.7.59](https://github.com/xypwn/filediver/blob/v0.7.59/extractor/unit/extractor.go); the full offline evidence remains in the research workspace.

## Compatibility and validation

The add-on continues to require Bingus Shared Loader v15+ and the game's own Stingray table. It does not require HD2Runtime, add terrain queries, cap active guides, or bundle the separately installed Helmet Headlamp resource or controller. The optional native-light switch defaults off.

Fresh validation completed: 216 offline tests passed, and all seven packaged Lua resources passed the LuaJIT source gates. The ZIP was then verified against the working source, package manifest and prior terrain payloads:

- Offline tests: `python -m unittest discover -s tests -v`
- LuaJIT and package gates: `python -B work/standalone/build_probe.py --validate-only`
- Package structural checks: `python -B work/standalone/verify_package.py`
- Package: `dist/HD2-EagleDirectionProbe-1.10.0-rc10.zip`
- ZIP size: 2,218,662 bytes
- SHA-256: `81a10cdc309b78525482bb6261c19932f985ab76af316f313b8485f466576b9d` (also recorded in `dist/SHA256SUMS-1.10.0-rc10.txt`)
- `src/terrain_query.lua`: 7,880 bytes, SHA-256 `fe382d64d5d6f7ad76e78192e1cd3b4ebc1f6a8af9c1616e063d524b3e74c8cc`, byte-identical to `v1.9.10`.
- `src/terrain_contract.lua`: 1,507 bytes, SHA-256 `f20654bf5934244d85639438c6a52674c4cf3d9f47ef73a288dfe364362f6017`, byte-identical to `v1.9.10`.
