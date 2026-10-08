"""Counterfactual: does the trail hold actually fix the blinking?

Copies the probe, sets TRAIL_HOLD_S to 0 (the old behaviour: one empty sample wipes the
track), and runs the same flaky-aircraft scenario against both. If the copy blinks and the
real source does not, the fix is doing the work - rather than the scenario being too kind.
"""
import os
import pathlib
import re
import tempfile

from lupa import LuaRuntime

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "mods" / "eagle-direction-probe" / "src" / "eagle_direction_probe.lua"
HARNESS = pathlib.Path(__file__).resolve().parent / "harness_draw.lua"
src = HARNESS.read_text(encoding="utf-8")

work = pathlib.Path(tempfile.mkdtemp(prefix="eagle-counterfactual-"))
original = PROBE.read_text(encoding="utf-8")

variants = {
    "hold ON  (0.9.0, the fix)": original,
    "hold OFF (0.8.0, cleared on one empty sample)":
        re.sub(r"local TRAIL_HOLD_S = [\d.]+", "local TRAIL_HOLD_S = 0", original),
}

for name, text in variants.items():
    path = work / (re.sub(r"\W+", "_", name) + ".lua")
    path.write_text(text, encoding="utf-8")
    tmp = tempfile.mkdtemp(prefix="eagle-cf-")
    os.environ["DSH_HARNESS_TMP"] = tmp
    os.environ["DSH_PROBE_PATH"] = str(path)
    os.environ["DSH_HARNESS_MODE"] = "flaky"
    L = LuaRuntime(unpack_returned_tuples=True)
    print("---- %s ----" % name)
    L.execute(src)
    print()
