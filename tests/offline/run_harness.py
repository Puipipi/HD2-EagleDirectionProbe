"""Run the offline drawing harness in each failure mode and compare.

The goal is to stop guessing about the in-mission reports. Each mode is a hypothesis about
what the game actually did, and the numbers below say whether the fix holds up.
"""
import os
import pathlib
import tempfile

from lupa import LuaRuntime

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "mods" / "eagle-direction-probe" / "src" / "eagle_direction_probe.lua"
HARNESS = pathlib.Path(__file__).resolve().parent / "harness_draw.lua"

MODES = [
    ("normal", "the aircraft is always found"),
    ("flaky", "one query in four finds nothing (what the captured mission measured)"),
    ("worldchurn", "main_world() hands back a new table every call"),
    ("twoair", "TWO Eagles at once - a squadmate, or the Eagle Storm buff"),
]

src = HARNESS.read_text(encoding="utf-8")
for mode, why in MODES:
    tmp = tempfile.mkdtemp(prefix="eagle-harness-%s-" % mode)
    os.environ["DSH_HARNESS_TMP"] = tmp
    os.environ["DSH_PROBE_PATH"] = str(PROBE)
    os.environ["DSH_HARNESS_MODE"] = mode
    print("=" * 78)
    print("MODE %s - %s" % (mode, why))
    print("=" * 78)
    L = LuaRuntime(unpack_returned_tuples=True)
    L.execute(src)
    M = L.eval("HD2EagleDirectionProbe")
    if M is not None:
        print("  draw_error=%s  trail_error=%s  errors=%s  draw_off=%s"
              % (M["draw_error"], M["trail_error"], M["errors"], M["draw_off"]))
    print()
