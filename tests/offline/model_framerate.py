"""Model a realistic frame rate, so the harness can tell the two submit modes apart.

The harness ran at 20 fps while the corridor refreshes at CORRIDOR_HZ = 20 - so the geometry
changed on essentially every frame and "submit only on change" looked nearly as good as
"submit every frame" (79% vs 91%). The real game runs at 133-156 fps, where the geometry changes
once every 7 frames or so and the difference is the whole complaint.

FRAME_DT sets the simulated frame interval; the scenario's phase lengths are scaled so the same
amount of game time passes regardless.
"""
import pathlib
import re

FILES = [
    "work/eagle-direction-spike/harness_draw.lua",
    "mods/eagle-direction-probe/tests/offline/harness_draw.lua",
]
ROOT = pathlib.Path(__file__).resolve().parents[2]

OLD_ENV = "local MODE = os.getenv('DSH_HARNESS_MODE') or 'normal'"
NEW_ENV = ("local MODE = os.getenv('DSH_HARNESS_MODE') or 'normal'\n"
           "-- Simulated frame interval. The real game measured 133-156 fps; the default here\n"
           "-- stays at 20 fps for the older scenarios, and the counterfactuals set it.\n"
           "local FRAME_DT = tonumber(os.getenv('DSH_FRAME_DT')) or 0.05")

OLD_TICK = """local function tick(n)
    for _ = 1, n do
        -- Cleared at the START of the frame: whatever the probe does during it decides whether
        -- anything is on screen for it.
        FRAME_DISPATCHED, FRAME_HAS_LINES = false, false
        FAKE_TIME = FAKE_TIME + 0.05"""

NEW_TICK = """local function tick(n)
    -- n is in units of the old 20 fps frame, so scaling it keeps each phase's DURATION the same
    -- while the number of frames changes.
    local frames = math.max(1, math.floor(n * (0.05 / FRAME_DT)))
    for _ = 1, frames do
        -- Cleared at the START of the frame: whatever the probe does during it decides whether
        -- anything is on screen for it.
        FRAME_DISPATCHED, FRAME_HAS_LINES = false, false
        FAKE_TIME = FAKE_TIME + FRAME_DT"""

for name in FILES:
    path = ROOT / name
    t = path.read_text(encoding="utf-8")
    n = 0
    for old, new in ((OLD_ENV, NEW_ENV), (OLD_TICK, NEW_TICK)):
        if old in t:
            t = t.replace(old, new, 1)
            n += 1
        else:
            print("  %s: anchor missing -> %r" % (name, old[:44]))
    path.write_text(t, encoding="utf-8")
    print("%s: %d of 2 patches applied" % (name, n))
