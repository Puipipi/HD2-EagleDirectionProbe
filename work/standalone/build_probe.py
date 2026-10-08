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
VERSION = '1.9.7'
EXTRA_SOURCES = {
    'mods/codex/eagle_terrain_query': REPO / 'src/terrain_query.lua',
    'mods/codex/eagle_terrain_contract': REPO / 'src/terrain_contract.lua',
}

SCRIPT_EXTENSIONS = ('.bat', '.cmd', '.ps1', '.vbs', '.js', '.exe', '.dll')

README_TXT = """Eagle Direction Probe v{version} - corridor test candidate
=========================================================

WHAT THIS IS
  Draws the actual Eagle aircraft track, heading arrow and a warning strip at the
  settled stratagem beacon. Records positions for offline analysis. It does not
  modify gameplay values or use memory writes / HD2Runtime.
  Holographic style: filled white arrows, cyan accents, small travelling ground
  arrows, a compact filled landing diamond and five moving UPRIGHT sky arrows.
  Each sky arrow is a single vertical plane with a shaft and pointed head (->),
  14 m long and 6.4 m tall. Its centre floats 12 m above cached terrain, without
  borders. Both ground/sky move 6 m/s; motion is cached at 20 Hz.
  Filled silhouettes use dense scan lines on the verified LineObject renderer,
  not new native GUI/material calls; very close views can reveal scan lines.
  Ground and aircraft guides retire together on a confirmed departure climb,
  without waiting for the aircraft object to despawn. Live guide count has no
  numerical limit. Ground is 200 m long and visually 12 m wide. All its direction
  heads travel. The amber landing diamond is 2.8 m tall and wide. The stem extends
  220 m behind the aircraft; the arrow extends 120 m ahead.
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
  The sky has arrows ONLY, no boundary. Five rigid glyphs sit about 26 m above
  their locally sampled surface (beacon height fallback), along the incoming axis.
  Sky brightness flows gently forward. Ground arrows travel at 6 m/s, with their
  geometry cached at 20 Hz separately from static outlines; no extra ray queries.
  Mod Options Menu (optional): MODS > 飞鹰方向指引. Toggles: 透视显示 (OFF by
  default), 天空方向箭头 (ON), 地面走廊 (ON). Click Apply; the menu saves choices.
  Choices apply during a mission. Without the menu, these defaults are used.
  Hiding both sky and ground stops new terrain queries. The aircraft guide stays.

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
  Exact stratagem type is NOT identified: shared aircraft resources and zero
  munition-query hits cannot reliably distinguish Airstrike / Cluster / 500kg.
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
