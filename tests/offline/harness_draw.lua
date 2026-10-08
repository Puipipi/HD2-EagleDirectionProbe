-- Offline harness: drive the probe against a fake engine and inspect the corridor's state.
--
-- Written because the in-mission log said `segments=0` while the same session's samples
-- showed the aircraft visible for 174 ticks with a forward vector every time. The data was
-- there, so the bug had to be in the geometry code - and reading the code was not settling
-- it. This runs the real probe source, unmodified, against a scripted world.

local FAKE_TIME = 100.0
os.clock = function() return FAKE_TIME end
-- Read the paths BEFORE shadowing os.getenv: the first version of this harness shadowed it
-- with a function that only answered LOCALAPPDATA, so the probe path came back nil and
-- loadfile(nil) quietly read an empty stdin instead - the probe "loaded" and did nothing.
local tmp = os.getenv('DSH_HARNESS_TMP') or '.'
local probe_path = os.getenv('DSH_PROBE_PATH')
local MODE = os.getenv('DSH_HARNESS_MODE') or 'normal'
-- Simulated frame interval. The real game measured 133-156 fps; the default here
-- stays at 20 fps for the older scenarios, and the counterfactuals set it.
local FRAME_DT = tonumber(os.getenv('DSH_FRAME_DT')) or 0.05
local REAL_GETENV = os.getenv
os.getenv = function(name)
    if name == 'LOCALAPPDATA' then return tmp end
    if name == 'DSH_PROBE_PATH' then return probe_path end
    return REAL_GETENV(name)
end

-- ------------------------------------------------------------------ fake engine --
local V = setmetatable({
    x = function(v) return v[1] end,
    y = function(v) return v[2] end,
    z = function(v) return v[3] end,
}, { __call = function(_, x, y, z) return { x, y, z } end })

local COLORS = {}
local ADDED = {}          -- every add_line call, so we can count real submissions

local WORLD = { name = 'world' }
local BEACON = setmetatable({}, { __tostring = function() return '#ID[16f397ca5f51f271]' end })
local AIRCRAFT = setmetatable({}, { __tostring = function() return '#ID[4e401cc877093220]' end })
local AIRCRAFT2 = setmetatable({}, { __tostring = function() return '#ID[4e401cc877093220]' end })

local ST = {
    aircraft_up = false,
    beacon_arc = 0,        -- how many samples of the throw arc have been served
}

local function beacon_pos()
    -- A throw: fast for the first four samples, then settled on the ground for good.
    local n = ST.beacon_arc
    if n < 4 then
        return { 0 + n * 12, 0 + n * 8, 40 - n * 2 }
    end
    return { 48, 32, 32 }        -- landed, never moves again -> speed 0
end

local AIRCRAFT_N = 0
local function aircraft_pos()
    -- Moves every time it is read, like a real pass at ~200 m/s sampled at 5 Hz.
    AIRCRAFT_N = AIRCRAFT_N + 1
    local n = AIRCRAFT_N
    return { 600 - n * 30, -400 + n * 16, 900 - n * 50 }
end

local sr = {}
local EAGLE_QUERIES = 0
local CREATE_CALLS = 0
local DESTROY_CALLS = 0
sr.Application = {
    -- worldchurn: a NEW table every call. This is the hypothesis that the engine hands back a
    -- fresh wrapper each time, so comparing worlds by identity churns the line object. The
    -- Guard Dogs mod keys its line objects BY WORLD, which suggests identity is stable - but
    -- that is an inference, and one harness run settles it.
    main_world = function()
        if MODE == 'worldchurn' then return { name = 'world' } end
        return WORLD
    end,
    worlds = function() return { WORLD } end,
    time_since_launch = function() return FAKE_TIME end,
}
sr.World = {
    units_by_resource = function(_, key)
        if key == 'content/fac_helldivers/vehicles/eagle/eagle' then
            EAGLE_QUERIES = EAGLE_QUERIES + 1
            if not ST.aircraft_up then return {} end
            -- flaky: one query in four finds nothing, which is what the captured mission
            -- showed - 45 of 50 samples in one call, 34 of 44 in another.
            if MODE == 'flaky' and (EAGLE_QUERIES % 4 == 0) then return {} end
            -- twoair: two independently tracked Eagles, such as a squadmate's call.
            -- Both aircraft share one resource id, which is exactly why the probe has to key
            -- them by unit.
            if MODE == 'twoair' then return { AIRCRAFT, AIRCRAFT2 } end
            return { AIRCRAFT }
        end
        if key == '16f397ca5f51f271' then
            if ST.beacon_arc > 0 then return { BEACON } end
            return {}
        end
        return {}
    end,
    create_line_object = function(_, flag)
        CREATE_CALLS = CREATE_CALLS + 1
        return { flag = flag }
    end,
    destroy_line_object = function() DESTROY_CALLS = DESTROY_CALLS + 1 end,
}
sr.Unit = {
    world_position = function(unit)
        if unit == BEACON then return beacon_pos() end
        if unit == AIRCRAFT then return aircraft_pos() end
        if unit == AIRCRAFT2 then
            AIRCRAFT2_N = (AIRCRAFT2_N or 0) + 1
            return { -300 + AIRCRAFT2_N * 28, 500 - AIRCRAFT2_N * 12,
                     950 - AIRCRAFT2_N * 45 }
        end
        return nil
    end,
    world_pose = function(unit) return { unit = unit } end,
}
sr.Matrix4x4 = {
    forward = function() return { -0.5, 0.26, -0.82 } end,
}
-- Rendering semantics, modelled deliberately.
--
-- FRAME_DISPATCHED: dispatch is a PER-FRAME submission. A line object that is not dispatched in
-- this frame draws nothing in this frame - which is what the player described as "a pair of white
-- lines for an instant and then nothing", and what no previous harness run could see because the
-- fake object simply accumulated calls and forgot.
FRAME_DISPATCHED = false
FRAME_HAS_LINES = false
GROUND_LINES_SUBMITTED = 0
sr.LineObject = {
    reset = function()
        ADDED[#ADDED + 1] = 'reset'
        FRAME_HAS_LINES = false          -- reset clears what the object would draw
    end,
    add_line = function(_, color, a, b)
        assert(color ~= nil and a ~= nil and b ~= nil, 'invalid engine add_line argument')
        if color.a == 235 then GROUND_LINES_SUBMITTED = GROUND_LINES_SUBMITTED + 1 end
        ADDED[#ADDED + 1] = { color, a, b }
        -- Alpha 0 is the probe's way of hiding a line, so it does not count as visible.
        if color ~= nil and color.a ~= nil and color.a > 0 then FRAME_HAS_LINES = true end
    end,
    dispatch = function()
        ADDED[#ADDED + 1] = 'dispatch'
        FRAME_DISPATCHED = true
    end,
}
sr.Color = function(a, r, g, b)
    local c = { a = a, r = r, g = g, b = b }
    COLORS[#COLORS + 1] = c
    return c
end
sr.Vector3 = V
sr.Script = {
    temp_byte_count = function() return 0 end,
    set_temp_byte_count = function() end,
}
sr.Network = { game_session = function() return { session = true } end }
sr.GameSession = { in_session = function() return true end }
sr.IdString64 = { from_hex = function(hex) return hex end }
sr.IdString32 = { from_hex = function(hex) return hex end }
sr.Camera = {}
sr.Gui = {}
sr.Window = {}

_G.stingray = sr
_G.update = function() end
_G.shutdown = function() end

-- ------------------------------------------------------------------ load the probe --
for _,name in ipairs({'query','contract'}) do
    local path=probe_path:gsub('eagle_direction_probe%.lua$','terrain_'..name..'.lua')
    local module=loadfile(path)
    if module then package.preload['mods/codex/eagle_terrain_'..name]=module end
end
local chunk, err = loadfile(probe_path)
if chunk == nil then
    error('LOAD FAILED: ' .. tostring(err))
end
chunk()
local M = rawget(_G, 'HD2EagleDirectionProbe')
print('probe loaded: ' .. tostring(M and M.version) .. '  corridor enabled=' .. tostring(M and M.draw_enabled))
print('create_line_object flag chosen: ' .. tostring(M and M.through_world))

-- The probe refuses to touch the engine for STARTUP_GRACE_S after load, measured against
-- its own start time. My first harness ticked at 0.05 s per frame and never left the grace
-- period, so every read count stayed at zero and the drawing path never ran - the harness
-- was measuring its own mistake. Jump past the grace in one step.
FAKE_TIME = FAKE_TIME + 30

-- ------------------------------------------------------------------ drive it --
-- 20 fps, so a corridor refresh fires every frame and a 5 Hz log sample every fourth.
local OBS = { frames = 0, visible = 0, blinks = 0, was = 0, seg_sum = 0, stubs = 0 }
local function tick(n)
    -- n is in units of the old 20 fps frame, so scaling it keeps each phase's DURATION the same
    -- while the number of frames changes.
    local frames = math.max(1, math.floor(n * (0.05 / FRAME_DT)))
    for _ = 1, frames do
        -- Cleared at the START of the frame: whatever the probe does during it decides whether
        -- anything is on screen for it.
        FRAME_DISPATCHED, FRAME_HAS_LINES = false, false
        FAKE_TIME = FAKE_TIME + FRAME_DT
        _G.update()
        OBS.frames = OBS.frames + 1
        if FRAME_DISPATCHED and FRAME_HAS_LINES then
            OBS.render_visible = (OBS.render_visible or 0) + 1
        end
        local now_seg = M.seg_count or 0
        if now_seg > 0 then OBS.visible = OBS.visible + 1 end
        -- A blink is the corridor being on screen and then not: the thing the player reported
        -- as "drawn only a few times".
        if OBS.was > 0 and now_seg == 0 then OBS.blinks = OBS.blinks + 1 end
        -- A STUB is a corridor that exists but is too short to be the aircraft's track. This
        -- is the failure the old code produced: the track was wiped every few samples, so it
        -- never grew past one or two points and the "corridor" was a couple of segments.
        if now_seg > 0 then
            OBS.seg_sum = OBS.seg_sum + now_seg
            if now_seg < 40 then OBS.stubs = OBS.stubs + 1 end
        end
        OBS.was = now_seg
    end
end

local function report(tag)
    local tracks, pts, heads = 0, 0, 0
    for _, t in pairs(M.tracks) do
        tracks = tracks + 1
        pts = pts + #t.trail
        if t.heading then heads = heads + 1 end
    end
    local impacts = 0
    for _ in pairs(M.impacts) do impacts = impacts + 1 end
    print(string.format('%-18s tracks=%d points=%d headings=%d impacts=%d seg=%-4s submits=%d',
        tag, tracks, pts, heads, impacts, tostring(M.seg_count), M.submits or 0))
end

tick(30)
report('on the ship')

-- A throw, then a real flight: the beacon flies fast for four samples and settles; the
-- aircraft moves every sample and stays up for the rest of the run.
ST.beacon_arc = 1
ST.aircraft_up = true
tick(4)
report('right after throw')

ST.beacon_arc = 5
tick(60)
report('beacon settled')

ST.beacon_arc = 40
tick(200)
report('aircraft flying on')

-- The aircraft leaves: the corridor should disappear rather than freeze.
ST.aircraft_up = false
ST.beacon_arc = 0
tick(40)
report('aircraft gone')

print(string.format('  peak_draw=%.3f ms  draw_off=%s', M.draw_peak_ms or 0, tostring(M.draw_off)))
print(string.format('  RENDERED frames: %d of %d (%.0f%%) - dispatch in the same frame it had lines',
    OBS.render_visible or 0, OBS.frames,
    100.0 * (OBS.render_visible or 0) / math.max(OBS.frames, 1)))
print(string.format('SUMMARY mode=%s frames=%d visible=%d blinks=%d stubs=%d mean_seg=%.1f '
    .. 'line_created=%d line_destroyed=%d',
    MODE, OBS.frames, OBS.visible, OBS.blinks, OBS.stubs,
    OBS.visible > 0 and (OBS.seg_sum / OBS.visible) or 0,
    CREATE_CALLS, DESTROY_CALLS))


-- What was actually submitted: count add_line calls between the last reset and dispatch.
local lines = 0
for i = #ADDED, 1, -1 do
    if ADDED[i] == 'dispatch' then break end
    if type(ADDED[i]) == 'table' then lines = lines + 1 end
end
print(string.format('  add_line calls in the last submission: %d', lines))

-- Colour order check: print what the probe asked for, so ARGB vs RGBA is visible.
if COLORS[1] then
    print(string.format('  first sr.Color call: (%.0f, %.0f, %.0f, %.0f)',
        COLORS[1].a, COLORS[1].r, COLORS[1].g, COLORS[1].b))
end
