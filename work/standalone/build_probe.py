"""Build this mod into a mod-manager-importable ZIP.

Usage:
  python -B work/standalone/build_probe.py --validate-only   # gates only
  python -B work/standalone/build_probe.py                   # -> dist/

The envelope encoder it uses lives in this repo's own ``work/standalone/vendor/bingus/``
and is deliberately NOT committed (see THIRD_PARTY_NOTICES.md and the workspace
convention: every mod repo here tracks zero vendor files). Fetch it with the
``hd2-bingus-toolchain-setup`` skill if the directory is empty.

Gates, in the order the workspace's hd2-addon-build skill defines them:

  1. the source compiles on real LuaJIT 2.1 (via lupa). The loader silently skips a
     mod that exceeds LuaJIT's per-function instruction cap, so a plain-Lua compile
     (or no compile at all) is not acceptable evidence that the mod will load.
  2. no ``user32`` symbol in any ``ffi.cdef``. LuaJIT's C namespace is process-global
     and keeps the first declaration, so re-declaring one breaks other mods.
  3. the addon declaration line matches the resource name the envelope is keyed by.
  4. no script-like file inside the finished archive.

It never deploys. Deployment is a separate, deliberate step in the mod manager.
"""
import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
VENDOR = HERE / 'vendor' / 'bingus'

SOURCE = REPO / 'src' / 'eagle_direction_probe.lua'
COVER = REPO / 'assets' / 'cover.png'
DIST = REPO / 'dist'

RESOURCE = 'mods/codex/eagle_direction_probe'
GUID = '8664ae8e-edd8-438d-b036-85045aefe011'   # stable: reuse for every rebuild
DISPLAY_NAME = 'Eagle Direction Probe (read-only)'
VERSION = '1.10.0-rc15'
EXTRA_SOURCES = {
    'mods/codex/eagle_terrain_query': REPO / 'src/terrain_query.lua',
    'mods/codex/eagle_terrain_contract': REPO / 'src/terrain_contract.lua',
    'mods/codex/eagle_solid_renderer': REPO / 'src/solid_renderer.lua',
    'mods/codex/eagle_stratagem_query': REPO / 'src/stratagem_query.lua',
    'mods/codex/eagle_stratagem_profiles': REPO / 'src/stratagem_profiles.lua',
    'mods/codex/eagle_native_light_probe': REPO / 'src/native_light_probe.lua',
    'mods/codex/eagle_performance_clock': REPO / 'src/performance_clock.lua',
    'mods/codex/eagle_cordon_font': REPO / 'src/cordon_font.lua',
    'mods/codex/eagle_local_player_pose': REPO / 'src/local_player_pose.lua',
    'mods/codex/eagle_cordon_view': REPO / 'src/cordon_view.lua',
    'mods/codex/eagle_occlusion_outline': REPO / 'src/occlusion_outline.lua',
    'mods/codex/eagle_terrain_grid': REPO / 'src/terrain_grid.lua',
}

SCRIPT_EXTENSIONS = ('.bat', '.cmd', '.ps1', '.vbs', '.js', '.exe', '.dll')

README_TXT = """Eagle Direction Probe v{version} - corridor test candidate
=========================================================

WHAT THIS IS
  Draws the actual Eagle aircraft track, heading arrow and a warning strip at the
  settled stratagem beacon. Records positions for offline analysis. It does not
  modify gameplay values or use memory writes / HD2Runtime.
  Holographic style: filled white arrows, cyan accents, small travelling ground
  arrows, a compact filled landing diamond and 2-5 moving UPRIGHT sky arrows.
  Each sky arrow is a single vertical plane with a shaft and pointed head (->),
  14 m long and 6.4 m tall. Its centre floats 12 m above cached terrain, without
  borders. Both ground/sky move 10 m/s; arrows are cached at 20 Hz. Sky arrows
  wrap inside the current type-specific corridor ends; short ranges use fewer
  complete glyphs, never stretched arrows. The range MOM switch affects both.
  Ground triangles are 5.2 m long and 5.8 m wide. White ground borders are actual
  filled 0.5 m-wide bands in true-fill mode, subdivided on cached terrain.
  Circular references use a filled annulus. Line mode keeps the strand fallback.
  Spaced upright red hologram plates have cut corners, an opaque dark-red face and a
  slim lit rim. RC6 uses an opaque dark-red plate, rim and letters; every plate
  keeps its own specific REF name, or EAGLE ?.
  Empty long plates and near-beacon label/size reassignment are removed.
  Panels start 1.1 m above cached ground and are 1.35 m tall. Their size is fixed
  for a given name, independent of camera distance. Names are real filled strokes
  offset 4 cm outward from the plate, using the same GUI path as the plate.
  Each of the six moving plates keeps one complete label on the side facing the
  cached local-player pose. The 10 Hz panel rebuild samples the existing pose
  resolver once; if pose is unknown, the last side is kept or one inner side is used.
  Solid text keeps the verified single outward winding; line fallback uses the
  same selected copy. Actual game material culling and text readability remain unverified.
  Whole panels and attached names move forward at 10 m/s, using a separate 10 Hz
  mesh cache; intermediate arrow ticks reuse the full retained panel geometry.
  At the end, each whole plate/name wraps to the beginning with equal spacing.
  RC10 NATIVE LIGHT COMPATIBILITY: RC9's game log reported missing
  Light.set_spot_angle_start before the helper could spawn. The prototype now
  preserves the resource-authored cone/falloff, resolves four known functional
  lights by name, and treats num_lights/has_light/update_unit as optional.
  MOM 原生紫色投光对照测试（需头灯资源） still defaults OFF. The optional
  资源原始白光对照 mode skips color/intensity setters and rebuilds owned helpers.
  Requires the separately installed Helmet Headlamp 1.0.0 light resource, enabled
  through its mod-manager Default Mode resource option. No third-party assets or
  controller code are bundled. Normal direction guides do not need the headlamp.
  Creates an OWN light-only helper 12 m above each landing point, with the prototype's
  existing spotlight rotation. The actual beam direction and ground illumination are not
  validated; this is not a precise
  rectangular attack footprint or the Stingray's blue ground-marking effect.
  Original headlamp units/settings remain untouched. Missing resource/API means
  no spotlight; existing guides continue. Turn MOM off to remove owned lights.
  Native testing suppresses the old red face overlay for a clear comparison.
  By default, the colour comparison changes only the owned light RGB to (1,0,1),
  keeps intensity 7000, and leaves position, rotation and authored cone unchanged.
  The optional 资源原始白光对照 skips both color and intensity setters and rebuilds
  only owned helpers. Each world/mode captures one original/configured color,
  intensity, world-position and root-forward readback on its first successful helper.
  Getter failure is diagnostic only; root-forward does not prove the embedded beam axis.
  RC12 already attempted World.update_unit optionally, so rc13 added failure detection
  and readback; the cause of the invisible ground light remains unresolved.
  Neither purple nor authored-color ground visibility is confirmed.
  Creation is limited to one helper per frame, with no active-guide count cap.
  Stationary emitters receive no position/colour updates or extra terrain queries.
  The active target light receives one set_enabled(true) reassertion per render frame;
  due/dirty synchronization and cleanup run first. Only owned helpers are touched.
  Lights retire with guides, on disable, draw failure and shutdown. Scene teardown
  never destroys a unit through a dead world. Real illumination, optical axis,
  brightness and GPU cost still require a manual game test. This does not claim
  that the Stingray blue ground-marking implementation has been identified. Keep the prototype OFF.
  RC13 SAFETY AND DIAGNOSTICS: only a positive two-snapshot match to a known Eagle
  stratagem can bind the nearest aircraft or draw its ground, sky, cordon or native
  light guide. Unknown, unsupported, ambiguous or unavailable records remain
  candidates for polling and cannot borrow the nearest Eagle's heading. The separate
  aircraft arrow remains visible. A previously confirmed Eagle keeps its guide during
  temporary reader failure. Each beacon record gets an anonymous B# episode id in
  event and JSON trace/motion diagnostics; it can change after cleanup/prune and is
  not an engine Unit id. A one-shot startup
  snapshot lists visible native-light API member types at the main menu; it does not
  spawn a helper or call light getters/setters. After manual import and full restart,
  inspect %LOCALAPPDATA%/CowboyBingus/Helldivers2/Logs/EagleDirectionProbe.log.
  RC14 uses readable vector-stroke labels and one view-selected text copy per panel.
  Real-game text visibility/depth and purple ground illumination remain unverified.
  Native helpers use normalized colour plus intensity and report one-time owned-helper
  readback. The head-up local-player DANGER/PATH? warning and its polling were removed;
  cached player pose remains for selecting the visible text side and drawing self-test.
  The native probe reasserts its owned target light once per rendered frame, after
  due/dirty cleanup and synchronization. No other mod's light is touched.
  No Runtime or active-guide count cap is added.
  RC15 ground-border/strip vertices reuse axial stations from the existing cached terrain
  grid, with no extra collision queries; the two-query/frame and 0.5 ms soft budget remain.
  Main lines request depth testing; fill uses the existing world-GUI path, whose depth
  behavior is not verified. Through-world OFF submits no extra x-ray outline. ON keeps
  the GUI fill and adds a no-depth dashed component-outline pass without fill, scan-fill
  rows, or glyph fragments. Offline checks verify line flags and cleanup, but GUI depth
  ordering and pixel occlusion still need an in-game visual check. Normal visible text stays.
  Guide-work timing counts full Lua and draw work on frames with guide geometry or owned
  native lights; it is not a GPU/pixel visibility measure or game FPS. The 0.05 ms/frame
  goal remains unmet. Paired offline figures are medians of three run means. For 1/4/8
  guides with through-world OFF: rc14 0.0642/0.2457/0.4708 ms, rc15 0.0846/0.2969/
  0.5065 ms (an 8-32% regression). RC15 ON medians are 0.2631/0.8352/1.7510 ms; old ON
  forced a different line backend, so no ratio is claimed. These CPU-only
  checks do not measure in-game FPS/GPU or prove pixel visibility. Purple/authored headlamp
  behavior remains a manual game test.
  The 330 offline tests pass. All 13 Lua payloads pass LuaJIT 2.1 compile and source gates;
  terrain query/contract resources are byte-identical to v1.9.10.
  MOM 详细采样记录 defaults OFF; enabling it restores per-sample JSONL and
  once-per-call munition/idle-pose diagnostics, not required for visible guides.
  White borders/landing diamond stay static. Ground border/triangles now clear
  cached terrain by 0.08 m instead of 0.8 m; upright plates/diamond keep their old
  elevations. Coarse interpolation may still differ on uneven terrain.
  No extra collision queries are made.
  RC8 OPTIONAL GROUND AREA: MOM 地面红色范围光幕（测试） defaults OFF.
  Enable it together with adaptive reference ranges and true fill; see-through
  must be OFF. It adds a faint red translucent mesh inside an identified reference
  footprint, using the existing collision-height cache. This is an overlay, not
  a projected light or illumination of rocks/characters. Unknown types, 110mm,
  unavailable terrain and unsampled/missed cells have no red area.
  Rectangle cells and a subdivided 500kg disc stay static with the retained GUI.
  No scan-line fallback, extra raycasts or alpha animation. It retires with the guide.
  The existing ground-height slider also moves this area, 2 cm below arrows
  (minimum zero clearance). Turning it on adds retained triangles / GPU work;
  offline CPU timings do not measure game FPS or transparent-surface GPU cost.
  EXPERIMENTAL TYPES: independent bounded active-record snapshots at 5 Hz with
  live guides or a freshly thrown beacon in its existing settling window.
  Two consecutive unique ball/record position matches identify a
  candidate among eight Eagle types. Ambiguity keeps EAGLE ?. No Runtime needed.
  Aircraft direction and retirement still use actual flight tracking.
  RC5 starts matching before the settled guide is created. A fresh unknown candidate
  does not draw Eagle impact geometry; its aircraft arrow remains independent.
  A previously confirmed Eagle stays visible during a temporary reader failure.
  Classification uses the existing 5 Hz cadence with live candidates even if both
  name/range UI options are off; no candidate means no type query. Very late native
  records may still adapt later. Lost provisional beacons expire after 0.75 s
  and must settle/match afresh. A new throw never inherits a previous candidate.
  User-selected shared transverse REF: Airstrike, Cluster, Smoke, Gas and Napalm
  use 66.67 m total length and 20 m total width, centered on the same beacon and
  incoming heading. This is not a measured damage/fire boundary.
  These remain display references, not measured damage/safe boundaries. Strafing
  extends forward; 500kg uses a 25 m reference circle. 110mm target remains unknown:
  its generic direction guide is retained, labelled 110MM TARGET ?.
  MOM options 具体飞鹰名称（测试） and 按战备调整参考范围（测试） default ON.
  They save independently; classification still polls active candidates when both
  are disabled and does not query when there is no candidate.
  EXPERIMENTAL TRUE FILL: actual retained world-GUI triangles replace scan lines
  for aircraft arrows/shafts, sky shafts/heads, ground triangles, the diamond
  and moving panels, their rims/names, and white reference borders.
  RC3 fixes swapped distance/height in rc1/rc2: the complete native path needs
  XYZ for creation and XZY for updates. Earlier tests stopped at the Lua wrapper
  and missed the shared native vertex writer. Material/depth still need validation.
  MOM: 真正面填充（测试） defaults ON in this candidate. Turn it OFF to restore
  the line-fill renderer. Missing APIs also fall back. See-through keeps the existing
  world-GUI fill and adds only dashed component outlines; no unverified world-GUI depth
  override is used.
  Faces reuse retained IDs; unchanged immutable batches/records skip redundant
  validation and native updates. Cached panel templates merge collinear letter
  strokes and reuse triangle corners. Ground faces use
  cached-height subdivisions and make no additional terrain collision queries.
  RC6 shares three frame-local native vertices between opposed windings and
  builds native colours only when needed. The solid path caches Lua line lists;
  the line fallback uses its original batches without copying. Engine objects
  never survive across frames. Appearance, motion, query budgets and guide counts
  are unchanged except the lower ground clearance and spaced opaque two-sided plates above.
  Offline Lua timings are not a game FPS measurement.
  This is a separate test candidate; 1.9.10 remains the stable release.
  Ground and aircraft guides retire together on a confirmed departure climb,
  without waiting for the aircraft object to despawn. Live guide count has no
  numerical limit. Only confirmed known Eagle types draw an impact guide. A confirmed
  Eagle with adaptive range disabled uses the 200 m by 12 m generic corridor; unknown
  candidates do not draw an Eagle ground/sky/cordon guide. All its direction
  heads travel. The amber landing diamond is 2.8 m tall and wide. The stem extends
  220 m behind the aircraft; the arrow extends 120 m ahead.
  Ground/sky directions latch on low attack arrival after an observed descent:
  within 120 m horizontally and -30..130 m above this beacon. They no longer turn
  with pullout yaw that starts before the nose rises. Far approach stays live;
  the aircraft arrow keeps its live pose. Existing retirement timing is preserved.
  Coarse terrain mode queries the complete strip on a 10 m grid (63 points).
  All strips share a maximum of TWO queries per frame and a 0.5 ms soft budget.
  Heights are cached; small steering corrections do not restart sampling.
  Resumed beacon flight withdraws a provisional landing without retiring it.
  Resource query gaps may recover within the original unbound lifetime. A new
  throw from a retired object starts a fresh strike record.
  Unsampled/missed portions are omitted until valid heights are available.
  The amber upright marker stays at the actual beacon, including during sampling.
  Warning lines USE DEPTH TESTING by default (no see-through). If the guarded native query
  is unavailable, the old beacon interpolation is used and the reason is logged.
  No Runtime mod is required; no BTO mod is required at runtime.
  Separate thrown beacons own separate strips, independent of the logging call.
  Ground arrow sides also bend along the cached samples, without extra queries.
  The sky has arrows ONLY, no boundary. Five rigid glyph centres sit 12 m above
  their locally sampled surface (beacon height fallback), along the incoming axis.
  Sky brightness flows gently forward. Ground arrows travel at 10 m/s, with their
  geometry cached at 20 Hz separately from static outlines; no extra ray queries.
  Mod Options Menu (optional): MODS > 飞鹰方向指引. The head-up local-player warning
  was removed; old saved warn_player values are ignored. Toggles: 详细采样记录 (OFF),
  透视显示 (OFF) by
  default), 飞鹰指示箭头 (ON), 天空方向箭头 (ON), 地面走廊边框 (ON),
  地面走廊三角 (ON), 红色全息警戒带 (ON), 真正面填充（测试） (ON),
  具体飞鹰名称（测试） (ON), 按战备调整参考范围（测试） (ON),
  原生紫色投光对照测试（OFF), 资源原始白光对照 (OFF).
  Ground-height slider 地面指引离地高度（厘米）: 0-100 cm in 1 cm steps,
  default 8 cm. Apply to update existing borders and ground triangles, and save.
  Sky arrows, plates and the landing diamond keep their independent heights.
  Zero clearance may cause coplanar flicker. No additional terrain casts occur.
  The red tape follows the border switch.
  Click Apply; the menu saves choices. Either ground option
  shows the landing diamond. Hiding the aircraft arrow also hides its trail.
  Choices apply during a mission. Without the menu, these defaults are used.
  Saved choices are restored before synchronizing defaults, as in Stratagem Cooldown.
  Hiding both sky and ground stops new terrain queries.
  Ground geometry is cached independently of aircraft movement. Scalar height
  interpolation and shared animation signatures reduce Lua CPU/allocations;
  query budgets are preserved. New borders/triangles/tape/text increase default
  line submissions; actual game rendering cost is unverified. Motion also adds
  cached Lua geometry work. Disable the red tape option to reduce this work.

STATUS
  Test candidate, not validated in a real mission. Fixes a ground-segment colour
  key mismatch (nil passed to add_line in 1.7.0, all ground lines skipped in 1.8.0)
  and LuaJIT JSON serialization. Native crashes are not caught by pcall.
  The warning strip is not a measured damage footprint. Aircraft-to-beacon
  matching is heuristic. Collision sampling is coarse, and narrow rocks or sharp
  ridges between samples can still intersect the warning. Vertical queries can
  hit roofs/objects above the underlying terrain. It is not a terrain mesh.
  Only the audited current game build is supported by the native query. Different
  code/build/world/preset checks fail closed. No guessed native address is called.
  The soft budget cannot interrupt an individual native query. Actual game query
  timing and mission appearance still need verification; no FPS claim is made.
  Per-call type matching is spatial and experimental, not a unique native event ID.
  A confirmed label stays with its guide through record/query loss until guide
  retirement or a mission/world change. Unknown calls never inherit that label.
  Overlapping calls stay unknown. Reference lengths/widths are baseline estimates,
  not a measured full damage envelope; upgrades/scatter/targeting remain unverified.
  Eagle Storm is NOT mission-validated. Aircraft using the recognized resource
  can get air guides independently of beacons. Without an ordinary beacon there
  is no reliable ground landing point; nearest-aircraft matching remains heuristic.

HOW TO USE
  1. Enable this mod and Bingus Shared Loader. Deploy. Start a mission.
  2. Call any Eagle stratagem (Airstrike, Cluster, Napalm, Strafing Run, Smoke,
     Gas, 110mm Rocket Pods) three or four times, FROM DIFFERENT ANGLES - vary the
     player-to-beacon bearing, or the analysis cannot tell the two candidate rules
     apart. 500kg is a single bomb with no run axis, so do not rely on it alone.
  3. Prefer OPEN TERRAIN for the baseline: the Eagle is reported to avoid
     obstacles, and a deflection would otherwise be mistaken for the rule being
     wrong. If you want to see that avoidance, deliberately call one strike toward
     a large piece of cover and remember which call it was.
  4. Verify a continuous white aircraft arrow and ground strip, then leave the
     mission. Check the log for errors. Samples are flushed during recording.

WHERE THE RESULTS GO
  %LOCALAPPDATA%\\CowboyBingus\\Helldivers2\\Logs\\EagleDirectionProbe-<timestamp>.jsonl
      one JSON record per sample: beacon positions, Eagle unit positions and
      forward vectors. This is the file the offline analyzer reads.
  %LOCALAPPDATA%\\CowboyBingus\\Helldivers2\\Logs\\EagleDirectionProbe.log
      human-readable: the stingray capability line, each call's start and end,
      and a shutdown summary.
      Terrain diagnostics: attempts, hits, frame_max, query_peak and total_peak.

  The first log line also settles a side question by measurement: whether the
  engine's `stingray` table is present independently of any other runtime mod.

IF THE EAGLE IS NEVER LISTED
  The probe finds the aircraft by the resource path
  content/fac_helldivers/vehicles/eagle/eagle. If the loader's resource query
  returns nothing for it, set FALLBACK_WORLD_SCAN = true near the top of the
  source and rebuild. That path walks the whole world (about 22,000 units) to
  find Eagle units by identity instead, in chunks of 2,000, and only while a call
  is live - it exists because the resource query is known to return an empty table
  for some units that do exist, and because walking the whole world while reading
  every position has crashed this game before.

IF A CALL LOOKS "WRONG"
  The Eagle is reported to avoid obstacles, so its approach direction changes when
  something is in the way. That means a strike that does not match the geometry is
  not automatically evidence that the geometry is wrong - it may be one deflected
  call. Note which calls were aimed toward large cover; the analyzer needs that
  from you, because coarse vertical heights do not establish the damage footprint.
""".format(version=VERSION)


def gate_declaration(source_bytes, resource=RESOURCE):
    expected = ('-- HD2-Addon: ' + resource + '\n').encode('utf-8')
    first, sep, _ = source_bytes.partition(b'\n')
    if not sep or first.rstrip(b'\r') != expected[:-1].rstrip(b'\r'):
        raise SystemExit('gate 3 FAILED: the addon declaration line does not match '
                         '%r' % resource)
    return 'gate 3 ok: declaration matches the resource name'


def gate_luajit(source_bytes):
    try:
        from lupa.luajit21 import LuaRuntime
    except ImportError:
        raise SystemExit('gate 1 FAILED: lupa is not installed; refusing to package '
                         'without a real LuaJIT compile (pip install -r '
                         'requirements-dev.txt)')
    try:
        LuaRuntime().compile(source_bytes.decode('utf-8'))
    except Exception as exc:
        raise SystemExit('gate 1 FAILED: LuaJIT compile error: %s' % exc)
    return 'gate 1 ok: LuaJIT 2.1 compile'


def gate_no_user32(source_bytes):
    text = source_bytes.decode('utf-8')
    for block in re.findall(r'ffi\.cdef\s*\[\[(.*?)\]\]', text, re.S):
        if 'user32' in block:
            raise SystemExit('gate 2 FAILED: ffi.cdef declares a user32 symbol')
    return 'gate 2 ok: no user32 in ffi.cdef'


def gate_archive(path):
    with zipfile.ZipFile(path) as package:
        for name in package.namelist():
            if name.lower().endswith(SCRIPT_EXTENSIONS):
                path.unlink()
                raise SystemExit('gate 4 FAILED: %s is a script-like file; the '
                                 'archive was deleted' % name)
    return 'gate 4 ok: no script-like file in the archive'


def run_source_gates():
    source = SOURCE.read_bytes()
    if source.startswith(b'\xef\xbb\xbf') or b'\0' in source:
        raise SystemExit('the source must be plaintext UTF-8 without a BOM')
    checks=[gate_declaration(source), gate_luajit(source),gate_no_user32(source)]
    for resource,path in EXTRA_SOURCES.items():
        extra=path.read_bytes()
        checks.extend([gate_declaration(extra,resource),gate_luajit(extra),gate_no_user32(extra)])
    return source,checks


def build():
    sys.path.insert(0, str(VENDOR))
    try:
        from archive import ARCHIVE, make_archive, resource_hash
    except ImportError as exc:
        raise SystemExit('the Bingus envelope encoder is missing at %s (%s). It is '
                         'not committed by convention; see THIRD_PARTY_NOTICES.md.'
                         % (VENDOR, exc))

    source, checks = run_source_gates()

    # The envelope encoder re-adds the declaration line itself, so strip it here.
    body = source
    if body.startswith(b'-- HD2-Addon:'):
        _, _, body = body.partition(b'\n')
    entry = ('-- HD2-Addon: ' + RESOURCE + '\n').encode('utf-8') + body

    resource = struct.pack('<II', len(entry), 2) + entry
    resources={resource_hash(RESOURCE): resource}
    for name,path in EXTRA_SOURCES.items():
        extra=path.read_bytes()
        resources[resource_hash(name)]=struct.pack('<II',len(extra),2)+extra
    blob = make_archive(resources)

    description = ('Test candidate: draws actual Eagle tracks, heading arrows and beacon '
                   'warning strips; records positions without modifying gameplay values. '
                   'Mission validation pending. Requires '
                   'Bingus Shared Loader v15 or newer / API 1.')
    manifest = {
        'Version': 1, 'Guid': GUID, 'Name': DISPLAY_NAME, 'Description': description,
        'IconPath': 'cover.png',
        'Options': [{'Name': DISPLAY_NAME, 'Description': description,
                     'Include': ['Addon'], 'Image': 'cover.png'}],
    }

    files = {
        'manifest.json': (json.dumps(manifest, indent=2) + '\n').encode('utf-8'),
        'Addon/' + ARCHIVE: blob,
        'Addon/' + ARCHIVE + '.stream': b'',
        'Addon/' + ARCHIVE + '.gpu_resources': b'',
        'README.txt': README_TXT.replace('\n', '\r\n').encode('utf-8'),
        'cover.png': COVER.read_bytes(),
    }

    DIST.mkdir(parents=True, exist_ok=True)
    output = DIST / ('HD2-EagleDirectionProbe-%s.zip' % VERSION)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, content)

    checks.append(gate_archive(output))
    for line in checks:
        print(line)
    print('entry bytes      : %d' % len(entry))
    print('archive bytes    : %d' % len(blob))
    print('resource hash    : 0x%016X' % resource_hash(RESOURCE))
    print('built            : %s (%d bytes)' % (output, output.stat().st_size))
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--validate-only', action='store_true',
                    help='run the source gates and stop before packaging')
    args = ap.parse_args()
    if args.validate_only:
        _, checks = run_source_gates()
        for line in checks:
            print(line)
        print('validate-only: gates passed, nothing packaged')
        return 0
    build()
    return 0


if __name__ == '__main__':
    sys.exit(main())
