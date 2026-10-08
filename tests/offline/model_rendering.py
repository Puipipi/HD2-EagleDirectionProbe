"""Give the harness's fake line object RENDERING semantics, not just data-flow semantics.

The gap I admitted: the harness modelled the geometry but not the drawing, so every offline run
reported 300+ visible frames while the game showed a one-frame flash. A line object that is
dispatched in frame N is visible in frame N and NOT in frame N+1 unless dispatched again - that
one sentence is the whole difference, and it is now in the fake engine.

With it, the player's report becomes reproducible offline, and the fix becomes testable.
"""
import pathlib

FILES = [
    "work/eagle-direction-spike/harness_draw.lua",
    "mods/eagle-direction-probe/tests/offline/harness_draw.lua",
]
ROOT = pathlib.Path(__file__).resolve().parents[2]

OLD_LINES = """sr.LineObject = {
    reset = function() ADDED[#ADDED + 1] = 'reset' end,
    add_line = function(_, color, a, b) ADDED[#ADDED + 1] = { color, a, b } end,
    dispatch = function() ADDED[#ADDED + 1] = 'dispatch' end,
}"""

NEW_LINES = """-- Rendering semantics, modelled deliberately.
--
-- FRAME_DISPATCHED: dispatch is a PER-FRAME submission. A line object that is not dispatched in
-- this frame draws nothing in this frame - which is what the player described as "a pair of white
-- lines for an instant and then nothing", and what no previous harness run could see because the
-- fake object simply accumulated calls and forgot.
FRAME_DISPATCHED = false
FRAME_HAS_LINES = false
sr.LineObject = {
    reset = function()
        ADDED[#ADDED + 1] = 'reset'
        FRAME_HAS_LINES = false          -- reset clears what the object would draw
    end,
    add_line = function(_, color, a, b)
        ADDED[#ADDED + 1] = { color, a, b }
        -- Alpha 0 is the probe's way of hiding a line, so it does not count as visible.
        if color ~= nil and color.a ~= nil and color.a > 0 then FRAME_HAS_LINES = true end
    end,
    dispatch = function()
        ADDED[#ADDED + 1] = 'dispatch'
        FRAME_DISPATCHED = true
    end,
}"""

OLD_TICK = """local function tick(n)
    for _ = 1, n do
        FAKE_TIME = FAKE_TIME + 0.05
        _G.update()
        OBS.frames = OBS.frames + 1"""

NEW_TICK = """local function tick(n)
    for _ = 1, n do
        -- Cleared at the START of the frame: whatever the probe does during it decides whether
        -- anything is on screen for it.
        FRAME_DISPATCHED, FRAME_HAS_LINES = false, false
        FAKE_TIME = FAKE_TIME + 0.05
        _G.update()
        OBS.frames = OBS.frames + 1
        if FRAME_DISPATCHED and FRAME_HAS_LINES then
            OBS.render_visible = (OBS.render_visible or 0) + 1
        end"""

OLD_SUM = """print(string.format('SUMMARY mode=%s frames=%d visible=%d blinks=%d stubs=%d mean_seg=%.1f '"""
NEW_SUM = """print(string.format('  RENDERED frames: %d of %d (%.0f%%) - dispatch in the same frame it had lines',
    OBS.render_visible or 0, OBS.frames,
    100.0 * (OBS.render_visible or 0) / math.max(OBS.frames, 1)))
print(string.format('SUMMARY mode=%s frames=%d visible=%d blinks=%d stubs=%d mean_seg=%.1f '"""

for name in FILES:
    path = ROOT / name
    t = path.read_text(encoding="utf-8")
    n = 0
    for old, new in ((OLD_LINES, NEW_LINES), (OLD_TICK, NEW_TICK), (OLD_SUM, NEW_SUM)):
        if old in t:
            t = t.replace(old, new, 1)
            n += 1
        else:
            print("  %s: anchor missing -> %r" % (name, old[:50]))
    path.write_text(t, encoding="utf-8")
    print("%s: %d of 3 patches applied" % (name, n))
