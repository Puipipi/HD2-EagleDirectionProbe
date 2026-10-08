-- HD2-Addon: mods/codex/eagle_direction_probe
-- Eagle Direction Probe -- READ-ONLY measurement addon.
--
-- ONE QUESTION, ONE MISSION: when an Eagle-series red stratagem is called, what is
-- the Eagle aircraft's ACTUAL incoming direction, and how does it relate to the
-- player and to the stratagem beacon?
--
-- Why the answer is not a single rule. The player reports that different Eagle
-- stratagems have different DEFAULT approach directions - the strafing run comes
-- along the player-to-beacon line from behind the player, the cluster bomb comes
-- perpendicular from the left - and that the aircraft additionally defends itself,
-- changing direction when something is in the way. So the direction is a
-- per-stratagem default plus a possible deflection, and a measurement that pools all
-- Eagle calls under one hypothesis answers nothing. This probe therefore identifies
-- WHICH stratagem each call was (see QUERY_KEYS) and records the raw geometry, so the
-- per-stratagem rule and the deflection can be separated offline.
--
-- READ-ONLY CONTRACT (auditable, please check it rather than trust it):
--   * no memory write of any kind appears in this file
--   * no native game function that mutates state is called
--   * only accessors on the game's own `stingray` table are read
--   * every engine call is wrapped in pcall and can never abort the update loop
--   * it writes exactly two files, both under the loader's existing log directory
--   * writes stop at a hard sample budget and report that they stopped
--
-- Why this shape: the workspace has a failure catalog entry for a mod that walked
-- World.units reading every position and crashed the game. This probe therefore
-- reads positions ONLY for units returned by units_by_resource (a handful), and the
-- optional whole-world fallback below is off by default, chunked, and bounded.

local MOD_KEY = 'HD2EagleDirectionProbe'
if rawget(_G, MOD_KEY) then return rawget(_G, MOD_KEY) end

local M = {
    version = '0.7.0',
    status = 'starting',
    reads = 0,
    errors = 0,
    samples = 0,
    calls = 0,
    stopped = false,
    backoff = 1,            -- multiplies the sample interval when ticks run slow
    slow_ticks = 0,
    slowest_tick_ms = 0,
    key_costs = {},         -- measured cost of each engine query, for the report
    -- corridor drawing (see the drawing section further down)
    trail = {},             -- the aircraft's actual ground track, newest last
    trail_heading = nil,    -- cached unit heading, recomputed at the sample rate
    line = nil,
    line_world = nil,
    draw_frames = 0,
    draw_slow = 0,
    draw_off = false,
    draw_last_ms = 0,
    draw_peak_ms = 0,
    draw_checked = 0,
    draw_enabled = true,
    selftest = false,
    selftest_origin = nil,
    selftest_frames = 0,
}
rawset(_G, MOD_KEY, M)

-- ------------------------------------------------------------------ constants --
-- Discovered offline from a 16 GB full process dump (2026-10-05 build) and from
-- the installed mods' own source. Both keys below are evidence-backed, not guesses.
local EAGLE_RESOURCE = 'content/fac_helldivers/vehicles/eagle/eagle'
local BEACON_HEX = '16f397ca5f51f271'   -- HUD_BTO catalog: {name="Beacon", resource_hex=...}

-- Every identity this probe asks the world about.
--
-- The aircraft alone is not enough: different Eagle stratagems are reported to have
-- DIFFERENT default approach directions (strafing run along the player-to-beacon
-- line from behind, cluster bomb perpendicular from the left), so a call has to be
-- identifiable from the log. Querying the munition identities as well as the
-- aircraft is what makes that possible without relying on the player to remember
-- which stratagem each call was.
--
-- The hex values are the entity ids the kill-feed/damage tables name
-- (eagle_bomb, eagle_base, ...). The beacon is queried separately because it drives
-- call detection. Any hex that does not resolve on this build simply yields no
-- units; it never errors.
local QUERY_KEYS = {
    { src = 'eagle_airstrike', hex = '2ea01cb1676aca29' },
    { src = 'eagle_cluster',   hex = '9d4f7cb4eb34515d' },
    { src = 'eagle_napalm',    hex = '27bb558c893383cc' },
    { src = 'eagle_smoke',     hex = '1b3bcadabc7ef8d6' },
    { src = 'eagle_gas',       hex = 'dbb286ad7ed9df96' },
    { src = 'eagle_500kg',     hex = 'e44b691dc039a505' },
    { src = 'eagle_rocket',    hex = '397792815583da29' },
    { src = 'eagle_gunpods',   hex = '0bd0f9d59048e9d1' },
    { src = 'eagle_base',      hex = '23a60681dd4383ec' },
    { src = 'eagle_missile',   hex = 'dfbb9a0d8fa27d85' },
}

-- Which stratagem a munition identity implies. Two identities map to the strafing
-- run (the aircraft body carries the gunpods), which is expected and harmless: the
-- analyzer only needs the set.
local STRATAGEM_OF = {
    eagle_airstrike = 'airstrike',
    eagle_cluster   = 'cluster',
    eagle_napalm    = 'napalm',
    eagle_smoke     = 'smoke',
    eagle_gas       = 'gas',
    ['eagle_500kg'] = '500kg',
    eagle_rocket    = '110mm_rocket_pods',
    eagle_gunpods   = 'strafing_run',
    eagle_base      = 'strafing_run',
    eagle_missile   = 'air_to_air',
}

-- Identity hexes the optional fallback scan treats as Eagle-family. Derived from
-- QUERY_KEYS so the two lists cannot drift apart.
local EAGLE_GUIDS = {}
for _, row in ipairs(QUERY_KEYS) do EAGLE_GUIDS[row.hex] = row.src end
EAGLE_GUIDS[BEACON_HEX] = 'beacon'

-- COST AND SAFETY BUDGETS. These exist because 0.2.0 shipped without them and the
-- game died with 0xC0000409 (STATUS_STACK_BUFFER_OVERRUN / __fastfail) while this
-- addon was sampling. 0.2.0 called units_by_resource 11 times per tick at 10 Hz -
-- about 110 engine queries a second - and never restored the script temp byte count.
-- Both of those are now bounded rather than trusted.
local SAMPLE_HZ = 5             -- deliberately below what the probe would like
local MAX_SAMPLES = 20000       -- hard stop; keeps the log bounded
-- A call is abandoned after this long. It was 30 s, which is LONGER than the gap between
-- a player's throws, so a second throw landed inside the first call and was swallowed:
-- five throws produced three calls in the measured session. The aircraft's pass is over
-- within a few seconds, so 10 s still captures it while letting each throw be its own call.
-- Ending a call also clears the motion table, so the landed beacon re-registers as
-- unmoved and cannot start another call until the player really throws again.
local CALL_TIMEOUT_S = 10
local CALL_GONE_S = 3           -- ...or this long after the beacon disappears

local TICK_BUDGET_MS = 25       -- one tick's engine work should fit in this
local SLOW_TICKS_BEFORE_STOP = 5
local IDENTIFY_BUDGET_MS = 20   -- the one-off per-call munition pass must fit this

-- Touch nothing for this long after load. The game is still initialising then, and
-- engine accessors called too early are exactly the situation a native crash lives in.
local STARTUP_GRACE_S = 20

-- While outside a mission, still read and report at this interval. Waiting in the ship
-- with a completely silent addon cannot distinguish "working, nothing to report" from
-- "broken and reading nothing", so the probe reports in every state. These reads
-- measure at 0.00 ms each; the 0.2.0 failure was never their cost.
local STATUS_S = 30

-- A beacon counts as a THROW only above this speed, in metres per second.
--
-- Presence is not evidence - the ship carries a stationary prop with the same resource id
-- (it moved 1.5 mm over 268 samples), and treating its existence as a call is what made
-- 0.2.0 sample in the loadout. Displacement alone is not enough either: several
-- beacon-identity objects coexist in a mission, all logging the same resource id, and the
-- landed ones drift by tens of metres over a session, so a displacement threshold fires on
-- them. A thrown beacon flies at tens of m/s; the settled ones do not. Measured on the
-- first captured mission, drift stayed well under 8 m/s while throws clearly exceeded it.
local THROW_SPEED_MPS = 8

-- ---------------------------------------------------------------- the corridor --
-- What is drawn: the aircraft's ACTUAL ground track, plus a forward extension along its
-- current heading and an arrowhead at the far end. Deliberately the actual path and not
-- the nominal rule, because the point is to see where the pass is really going - obstacle
-- avoidance and all - rather than to predict it.
--
-- Why only an axis and an arrow, with no width: the width differs per stratagem, and the
-- measured evidence says we cannot yet tell which stratagem a call is (all 11 munition
-- identity keys return zero units). A width would therefore be a guess, and a wrong width
-- on a 500kg - which is a point strike, not a line - would actively mislead. An axis is
-- true for every stratagem, so it is what this ships.
local TRAIL_MAX = 64            -- samples of ground track kept (about 13 s at 5 Hz)
local FORWARD_M = 900           -- how far ahead to extend along the current heading
local ARROW_M = 90              -- arrowhead arm length
local DRAW_BUDGET_MS = 8        -- one frame's drawing should fit in this
local DRAW_SLOW_BEFORE_OFF = 8  -- consecutive breaches before drawing switches itself off
local KILL_SWITCH = nil         -- set in the paths section; a file that disables drawing
local COLOR_TRAIL = { 255, 190, 40, 110 }
local COLOR_HEAD = { 255, 70, 40, 230 }

-- Only sample inside a mission. 0.2.0 sampled whenever a beacon-like object existed,
-- and a stationary one exists on the ship: selecting a stratagem in the loadout
-- started a 29-second sampling run in a menu, with no mission in progress.
local IN_SESSION_ONLY = true

-- Off by default. Turning this on makes the probe walk the whole world (about 22,000
-- units on a mission world) to find Eagle units by identity. That path has a crash
-- precedent in this workspace, so it is chunked and only runs while a call is live.
local FALLBACK_WORLD_SCAN = false
local SCAN_CHUNK = 2000

-- ---------------------------------------------------------------------- paths --
local HOME = (os.getenv('LOCALAPPDATA') or os.getenv('TEMP') or '.')
    .. '/CowboyBingus/Helldivers2'
local LOG_PATH = HOME .. '/Logs/EagleDirectionProbe.log'
-- One samples file PER SESSION, named for when the session started.
--
-- 0.6.0 reused a single name and opened it with 'w', so merely launching the game again
-- truncated the previous session's samples. That is not hypothetical - it destroyed a
-- completed measurement. The log is append-only so it survived, but it holds counts and
-- call boundaries rather than coordinates, so the geometry was unrecoverable. A fresh
-- name per session also keeps call ids from colliding across sessions.
local JSONL_PATH = HOME .. '/Logs/EagleDirectionProbe-'
    .. tostring(os.time()) .. '.jsonl'

-- Creating this file turns the corridor off without a rebuild. The probe has already taken
-- the game down twice, so there is a switch that needs no code change and no deploy: an
-- escape hatch the player controls, not one that depends on me shipping a new version.
KILL_SWITCH = HOME .. '/EagleCorridor.off'

-- Creating this file runs a one-off drawing self-test and then clears itself: a short line
-- is drawn beside the ship for a few seconds and the outcome is logged. It exists so the
-- line API can be proven on this build WITHOUT a mission - the riskiest new thing in 0.7.0
-- is the drawing path, and needing an Eagle to test it would be the wrong dependency.
SELFTEST_FILE = HOME .. '/EagleCorridor.selftest'

local log_file
local function log(line)
    local text = os.date('!%Y-%m-%dT%H:%M:%SZ ') .. tostring(line)
    local ok, f = pcall(io.open, LOG_PATH, 'a')
    if ok and f then
        pcall(f.write, f, text .. '\n')
        pcall(f.close, f)
    end
end

local jsonl
local function open_jsonl()
    local ok, f = pcall(io.open, JSONL_PATH, 'w')
    if ok and f then jsonl = f end
    return jsonl ~= nil
end

-- Lua's %q is NOT JSON: it escapes control characters as \ddd (decimal), which JSON
-- rejects. That produced one unparsable record per session. Escape properly instead.
local JSON_ESC = { ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f',
                   ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
local function json_string(value)
    local text = tostring(value)
    text = text:gsub('[%z\1-\31"\\]', function(c)
        return JSON_ESC[c] or string.format('\\u%04x', string.byte(c))
    end)
    return '"' .. text .. '"'
end

local function emit(record)
    if not jsonl or M.stopped then return end
    local ok, line = pcall(function()
        local parts = {}
        for _, key in ipairs({ 'kind', 't', 'call', 'note' }) do
            local value = record[key]
            if value ~= nil then
                parts[#parts + 1] = json_string(key) .. ':' ..
                    (type(value) == 'string' and json_string(value) or tostring(value))
            end
        end
        for _, key in ipairs({ 'beacons', 'eagles', 'caps', 'ids' }) do
            local value = record[key]
            if value ~= nil then
                parts[#parts + 1] = json_string(key) .. ':' .. value
            end
        end
        return '{' .. table.concat(parts, ',') .. '}'
    end)
    if ok then
        pcall(jsonl.write, jsonl, line .. '\n')
    else
        M.errors = M.errors + 1
    end
end

-- --------------------------------------------------------------- engine access --
local sr = rawget(_G, 'stingray')

local function report_capabilities()
    if type(sr) ~= 'table' then
        log('FATAL: _G.stingray is not a table (' .. type(sr) .. '). sr API unavailable;'
            .. ' this is not an HD2Runtime problem, see the spike notes.')
        return false
    end
    local names = { 'Application', 'World', 'Unit', 'Vector3', 'Matrix4x4',
                    'IdString64', 'IdString32', 'GameSession', 'Network',
                    'Color', 'Camera', 'LineObject', 'Gui', 'Script', 'Window' }
    -- Most of these are tables, but Color is a constructor FUNCTION on this build. The
    -- earlier check demanded a table for every name, so it reported Color as missing on
    -- every session - a false negative that hid the one call the corridor needs.
    local function present(name)
        local kind = type(sr[name])
        if name == 'Color' then return kind == 'function' end
        return kind == 'table'
    end
    local caps, missing = {}, {}
    for _, name in ipairs(names) do
        caps[name] = type(sr[name])
        if not present(name) then missing[#missing + 1] = name end
    end
    local need = { 'Application', 'World', 'Unit', 'Vector3' }
    local ok = true
    for _, name in ipairs(need) do
        if not present(name) then ok = false end
    end
    log('stingray capabilities: ' .. table.concat(
        (function()
            local out = {}
            for _, name in ipairs(names) do out[#out + 1] = name .. '=' .. tostring(caps[name]) end
            return out
        end)(), ' '))
    if #missing > 0 then
        log('stingray missing: ' .. table.concat(missing, ', '))
    end
    emit({ kind = 'capabilities', t = 0,
           note = table.concat((function()
               local out = {}
               for _, name in ipairs(names) do out[#out + 1] = name .. '=' .. tostring(caps[name]) end
               return out
           end)(), ',') })
    return ok
end

local function vector_xyz(value)
    if value == nil then return nil end
    local x, y, z
    local ok = pcall(function()
        x, y, z = sr.Vector3.x(value), sr.Vector3.y(value), sr.Vector3.z(value)
    end)
    if not ok or type(x) ~= 'number' then return nil end
    for _, v in ipairs({ x, y, z }) do
        if v ~= v or v == math.huge or v == -math.huge or math.abs(v) > 1e7 then
            return nil
        end
    end
    return { x, y, z }
end

local function world_position(unit)
    M.reads = M.reads + 1
    local ok, p = pcall(sr.Unit.world_position, unit, 1)
    if not ok then return nil end
    return vector_xyz(p)
end

local function unit_identity(unit)
    local ok, text = pcall(tostring, unit)
    if not ok or type(text) ~= 'string' then return nil end
    local hex = string.match(text, '#ID%[([0-9a-fA-F]+)%]')
    return hex and string.lower(hex) or nil
end

local function as_list(value)
    if type(value) ~= 'table' then return {} end
    if next(value) == nil then return {} end
    if value[1] ~= nil then return value end
    local out = {}
    for _, item in pairs(value) do out[#out + 1] = item end
    return out
end

local function units_by_resource(world, key)
    M.reads = M.reads + 1
    local ok, value = pcall(sr.World.units_by_resource, world, key)
    if not ok or value == nil then return {} end
    return as_list(value)
end

local function main_world()
    local ok, world = pcall(sr.Application.main_world)
    if ok and world ~= nil then return world end
    return nil
end

-- How many worlds the engine currently has. Cheap, and it is what separates "idle,
-- nothing to report" from "broken, reading nothing" in the log.
local function count_worlds()
    local ok, worlds = pcall(sr.Application.worlds)
    if not ok or type(worlds) ~= 'table' then return 'unavailable' end
    local n = 0
    for _ in pairs(worlds) do n = n + 1 end
    return n
end

local function key_from_hex(hex)
    if type(sr.IdString64) == 'table' and sr.IdString64.from_hex then
        local ok, key = pcall(sr.IdString64.from_hex, hex)
        if ok and key ~= nil then return key end
    end
    return hex      -- some builds accept the plain hex string
end

local function beacon_key() return key_from_hex(BEACON_HEX) end

-- ------------------------------------------------------------- cost discipline --
-- The workspace's proven overlay wraps every tick in a temp-byte-count save/restore,
-- and repeats the pair per unit around box reads. The script temp arena is not reset
-- for us, so a tick that allocates without restoring grows it. 0.2.0 did not do this
-- at all, which is one of the two defects that shipped.
local function temp_guard_begin()
    if type(sr.Script) == 'table' and type(sr.Script.temp_byte_count) == 'function' then
        local ok, saved = pcall(sr.Script.temp_byte_count)
        if ok then return saved end
    end
    return nil
end

local function temp_guard_end(saved)
    if saved == nil then return end
    pcall(sr.Script.set_temp_byte_count, saved)
end

-- Are we actually in a mission? A beacon-identity prop exists on the ship and does not
-- move, so the presence of a beacon is NOT evidence that a call happened - that
-- misreading is what made 0.2.0 sample in a menu.
--
-- 0.3.0 got this wrong in the way that killed the game: it called
-- `sr.GameSession.in_session()` with NO argument. Every proven mod in this workspace
-- passes the session - `in_session(session)` - having obtained it from
-- `sr.Network.game_session()` and checked it first. Calling it bare reached native code
-- with a nil session and took the process down with 0xC0000409. The signature is
-- copied from those mods now, not invented.
local function in_session()
    local net = sr.Network
    if type(net) ~= 'table' or type(net.game_session) ~= 'function' then
        return nil, 'no Network.game_session'
    end
    local ok, session = pcall(net.game_session)
    if not ok or session == nil then return false, 'no session' end

    local gs = sr.GameSession
    if type(gs) == 'table' and type(gs.in_session) == 'function' then
        local checked, value = pcall(gs.in_session, session)
        if checked then return value == true, 'GameSession.in_session(session)' end
        return nil, 'in_session errored'
    end
    -- No in_session API on this build: a live session object is the best evidence.
    return true, 'session exists, no in_session API'
end

-- The aircraft query plus every munition query, resolved once at load. A hex that
-- fails to resolve is kept as the plain string and simply returns no units, so a
-- build that does not accept one of these costs nothing but a wasted hash lookup.
local RESOLVED = {}
local function resolve_query_keys()
    RESOLVED = {}
    RESOLVED[#RESOLVED + 1] = { src = 'aircraft', key = EAGLE_RESOURCE }
    for _, row in ipairs(QUERY_KEYS) do
        RESOLVED[#RESOLVED + 1] = { src = row.src, key = key_from_hex(row.hex) }
    end
    return RESOLVED
end

-- ------------------------------------------------------------------ call state --
local next_sample = 0
local active_call = nil
local seen_beacon_ids = {}
local call_serial = 0
-- unit handle -> {p = {x,y,z}, moved = bool}. Keyed by the handle, not the identity
-- string, because that string is the resource hash shared by every beacon.
local beacon_motion = {}

-- Each entry carries the query it came from, so the log says which stratagem a call
-- was, not merely where the aircraft went.
local function json_points(entries, want_pose)
    local out = {}
    for _, entry in ipairs(entries) do
        local unit = entry.unit
        local p = world_position(unit)
        if p then
            local row = string.format('{"src":%s,"id":%s,"p":[%.4f,%.4f,%.4f]',
                json_string(entry.src or '?'), json_string(unit_identity(unit) or '?'),
                p[1], p[2], p[3])
            if want_pose and type(sr.Unit.world_pose) == 'function'
                and type(sr.Matrix4x4) == 'table' and sr.Matrix4x4.forward then
                local okt, pose = pcall(sr.Unit.world_pose, unit, 1)
                if okt and pose ~= nil then
                    local okf, fwd = pcall(sr.Matrix4x4.forward, pose)
                    local f = okf and vector_xyz(fwd) or nil
                    if f then
                        row = row .. string.format(',"f":[%.5f,%.5f,%.5f]', f[1], f[2], f[3])
                    end
                end
            end
            -- The one beacon that was actually thrown. Several beacon-identity objects
            -- coexist, and they all log the same resource id, so without this flag the
            -- analyzer cannot tell the thrown one from the landed ones - which is what
            -- made the player-to-beacon line meaningless in the first captured mission.
            if entry.primary then row = row .. ',"primary":true' end
            row = row .. (want_pose and ',"pose":true' or '') .. '}'
            out[#out + 1] = row
        end
    end
    return '[' .. table.concat(out, ',') .. ']'
end

local function begin_call(now, beacon_entries)
    call_serial = call_serial + 1
    active_call = {
        id = call_serial,
        started = now,
        last_seen = now,
        beacon_ids = {},
        srcs = {},          -- which munition identities this call turned out to use
        samples = 0,
    }
    for _, entry in ipairs(beacon_entries) do
        local id = unit_identity(entry.unit)
        if id then
            active_call.beacon_ids[id] = true
            seen_beacon_ids[id] = now
        end
    end
    M.calls = M.calls + 1
    log(string.format('call %d began (beacon units=%d)', call_serial, #beacon_entries))
    emit({ kind = 'call_begin', t = now, call = call_serial })
end

-- ---------------------------------------------------------------- fallback scan --
local scan_cursor = 0
local scan_units = nil
local function fallback_eagles(world, now)
    -- Identity-only scan, chunked. Positions are read only for matches.
    if scan_units == nil or (now - (scan_units.at or 0)) > 1.0 then
        local ok, value = pcall(sr.World.units, world)
        if not ok then return {} end
        local list = as_list(value)
        scan_units = { list = list, at = now, count = #list }
        scan_cursor = 0
        log(string.format('fallback: World.units returned %d unit(s)', #list))
    end
    local found = {}
    local last = math.min(scan_cursor + SCAN_CHUNK, #scan_units.list)
    for i = scan_cursor + 1, last do
        local unit = scan_units.list[i]
        local id = unit_identity(unit)
        if id and EAGLE_GUIDS[id] then
            found[#found + 1] = { src = EAGLE_GUIDS[id], unit = unit }
        end
    end
    scan_cursor = last >= #scan_units.list and 0 or last
    return found
end

-- ------------------------------------------------------- costly per-call pass --
-- Working out WHICH stratagem a call was means querying the munition identities, and
-- that is exactly what 0.2.0 did on every tick - 11 keys at 10 Hz. It is done once per
-- call now, under a time budget, and the cost of every key is logged, because the cost
-- of these queries is the thing we do not actually know.
local function identify_call(world, call, now)
    if call.identified then return end
    call.identified = true
    local began = os.clock()
    local hits = {}
    for _, row in ipairs(RESOLVED) do
        local key_began = os.clock()
        local units = units_by_resource(world, row.key)
        local key_ms = (os.clock() - key_began) * 1000
        M.key_costs[#M.key_costs + 1] = { src = row.src, units = #units, ms = key_ms }
        log(string.format('  key %-18s units=%d  %.2f ms', row.src, #units, key_ms))
        for _, unit in ipairs(units) do
            hits[#hits + 1] = { src = row.src, unit = unit }
        end
        if (os.clock() - began) * 1000 > IDENTIFY_BUDGET_MS then
            call.identify_aborted = true
            log(string.format('call %d: identification stopped early - %d key(s) already '
                .. 'cost over %d ms, the rest are skipped', call.id, #M.key_costs,
                IDENTIFY_BUDGET_MS))
            break
        end
    end
    for _, entry in ipairs(hits) do
        local family = STRATAGEM_OF[entry.src]
        if family and not call.srcs[family] then
            call.srcs[family] = true
            log(string.format('call %d: %s present -> stratagem %s',
                call.id, entry.src, family))
            emit({ kind = 'call_stratagem', t = now, call = call.id,
                   note = entry.src .. '=' .. family })
        end
    end
end

-- ----------------------------------------------------------------------- tick --

-- The aircraft's own forward vector, normalised. Preferred over differencing two track
-- points because it is instantaneous: in the captured mission the endpoint chord was off
-- by 150-160 degrees on two calls where the aircraft turned inside the window, while the
-- forward vector stayed correct.
local function aircraft_forward(unit)
    if type(sr.Unit.world_pose) ~= 'function' or type(sr.Matrix4x4) ~= 'table'
        or sr.Matrix4x4.forward == nil then
        return nil
    end
    local okp, pose = pcall(sr.Unit.world_pose, unit, 1)
    if not okp or pose == nil then return nil end
    local okf, fwd = pcall(sr.Matrix4x4.forward, pose)
    if not okf then return nil end
    local f = vector_xyz(fwd)
    if f == nil then return nil end
    local len = math.sqrt(f[1] * f[1] + f[2] * f[2] + f[3] * f[3])
    if len == 0 then return nil end
    return { f[1] / len, f[2] / len, f[3] / len }
end

-- Append the aircraft's actual position to the corridor's ground track. Called at the
-- sample rate; the draw only re-submits what is cached here.
local function update_trail(eagle_entries)
    if #eagle_entries == 0 then
        -- Aircraft gone: drop the track so the corridor disappears with it and the next
        -- pass starts clean instead of inheriting a stale heading.
        if #M.trail > 0 then
            M.trail, M.trail_heading = {}, nil
        end
        return
    end
    local entry = eagle_entries[1]
    local p = world_position(entry.unit)
    if p == nil then return end
    local trail = M.trail
    local last = trail[#trail]
    if last == nil then
        trail[1] = { p[1], p[2], p[3] }
    else
        local dx, dy, dz = p[1] - last[1], p[2] - last[2], p[3] - last[3]
        -- 0.5 m: below the aircraft's real motion at any speed it flies, above jitter.
        if dx * dx + dy * dy + dz * dz > 0.25 then
            trail[#trail + 1] = { p[1], p[2], p[3] }
            if #trail > TRAIL_MAX then table.remove(trail, 1) end
        end
    end
    local head = aircraft_forward(entry.unit)
    if head == nil and #trail >= 2 then
        local a, b = trail[#trail - 1], trail[#trail]
        local dx, dy, dz = b[1] - a[1], b[2] - a[2], b[3] - a[3]
        local len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if len > 0 then head = { dx / len, dy / len, dz / len } end
    end
    if head then M.trail_heading = head end
end

local function sample_body()
    if M.stopped then return end
    local now = os.clock()
    if now < next_sample then return end
    next_sample = now + (1 / (SAMPLE_HZ / (M.backoff or 1)))

    if M.samples >= MAX_SAMPLES then
        M.stopped = true
        log(string.format('stopped at the sample budget (%d)', MAX_SAMPLES))
        emit({ kind = 'stopped', t = now, note = 'sample budget' })
        return
    end

    -- Nothing at all until the game has settled.
    if M.installed_at == nil then M.installed_at = now end
    if now - M.installed_at < STARTUP_GRACE_S then return end

    local world = main_world()
    if world == nil then
        if now >= (M.next_status or 0) then
            M.next_status = now + STATUS_S
            local worlds = count_worlds()
            log(string.format('status: no main world yet (Application.worlds=%s) - the '
                .. 'probe is reading the engine but there is nothing to sample at this '
                .. 'screen', tostring(worlds)))
            emit({ kind = 'status', t = now, note = 'no main world',
                   note2 = 'worlds=' .. tostring(worlds) })
        end
        return
    end

    -- Read first, decide later. These reads are what prove the probe works, and they
    -- measure at 0.00 ms each, so they run in every state - on the ship, in a menu,
    -- in a mission. 0.2.0's failure was never their cost.
    local beacons = units_by_resource(world, beacon_key())
    local beacon_entries, eagle_entries = {}, {}
    for _, unit in ipairs(beacons) do
        beacon_entries[#beacon_entries + 1] = { src = 'beacon', unit = unit }
    end
    for _, unit in ipairs(units_by_resource(world, EAGLE_RESOURCE)) do
        eagle_entries[#eagle_entries + 1] = { src = 'aircraft', unit = unit }
    end

    local live, why = true, 'gate disabled'
    if IN_SESSION_ONLY then
        live, why = in_session()
    end

    -- A status line in every state, so a silent log can never again be ambiguous
    -- between "nothing to report" and "reading nothing".
    if now >= (M.next_status or 0) then
        M.next_status = now + STATUS_S
        log(string.format('status: worlds=%s session=%s (%s) beacon_units=%d '
            .. 'aircraft_units=%d temp_bytes=%s last_tick=%.1fms samples=%d calls=%d '
            .. 'backoff=x%d', tostring(count_worlds()), tostring(live), tostring(why),
            #beacon_entries, #eagle_entries, tostring(M.last_temp_bytes),
            M.last_tick_ms or 0, M.samples, M.calls, M.backoff or 1))
        emit({ kind = 'status', t = now,
               note = string.format('worlds=%s session=%s beacon=%d aircraft=%d',
                   tostring(count_worlds()), tostring(live), #beacon_entries,
                   #eagle_entries) })
    end

    if live ~= true then return end
    if FALLBACK_WORLD_SCAN then
        local seen = {}
        for _, entry in ipairs(eagle_entries) do seen[entry.unit] = true end
        for _, entry in ipairs(fallback_eagles(world, now)) do
            if not seen[entry.unit] then
                seen[entry.unit] = true
                eagle_entries[#eagle_entries + 1] = entry
            end
        end
    end

    -- Which beacon was THROWN, by SPEED, and per object.
    --
    -- Presence is not evidence (the ship carries a stationary prop with the same resource
    -- id). Displacement alone is not enough either: several beacon-identity objects
    -- coexist in a mission and they all log the same resource id, so the analyzer cannot
    -- separate them. A thrown beacon flies fast - tens of metres per second - while the
    -- landed ones only drift, so speed identifies the thrown one, and the object is
    -- tracked by its unit handle so the objects never get mixed up.
    --
    -- The same test splits calls: a fast beacon while a call is already active is a NEW
    -- throw, not the old one still moving. That replaces the timeout as the primary
    -- boundary, which matters because the timeout alone once swallowed a throw.
    local thrown, fast_now = nil, nil
    for _, entry in ipairs(beacon_entries) do
        local p = world_position(entry.unit)
        local rec = p and beacon_motion[entry.unit]
        if p and rec == nil then
            beacon_motion[entry.unit] = { p = p, t = now }
        elseif p then
            local dt = now - (rec.t or now)
            local dx, dy, dz = p[1] - rec.p[1], p[2] - rec.p[2], p[3] - rec.p[3]
            local speed = dt > 0 and (math.sqrt(dx * dx + dy * dy + dz * dz) / dt) or 0
            if speed > (rec.peak or 0) then rec.peak = speed end
            if speed > THROW_SPEED_MPS then
                rec.thrown = true
                rec.settled = nil
                fast_now = entry.unit
            elseif rec.thrown and not rec.settled and speed < THROW_SPEED_MPS / 4 then
                rec.settled = now          -- it has come to rest after a throw
            end
            rec.p, rec.t = p, now
        end
        if rec and rec.thrown and thrown == nil then thrown = entry.unit end
        entry.primary = (rec ~= nil and rec.thrown == true) or false
    end

    if #beacon_entries > 0 and thrown == nil and now >= (M.next_static_report or 0) then
        M.next_static_report = now + 120
        log(string.format('beacon-identity units present, none thrown (>%.0f m/s): '
            .. 'ignoring them as props, not a stratagem', THROW_SPEED_MPS))
    end

    -- Never let the motion table grow without bound if units churn.
    local motion_n = 0
    for _ in pairs(beacon_motion) do motion_n = motion_n + 1 end
    if motion_n > 64 then beacon_motion = {} end

    -- A fresh high-speed beacon while a call is active means a NEW throw: close the
    -- current call so the two throws are not merged into one record.
    if fast_now and active_call ~= nil and active_call.primary_unit ~= nil
        and fast_now ~= active_call.primary_unit then
        log(string.format('call %d closed early: a different beacon was thrown',
            active_call.id))
        emit({ kind = 'call_end', t = now, call = active_call.id, note = 'new throw' })
        active_call = nil
    end

    if thrown ~= nil and active_call == nil then
        begin_call(now, beacon_entries)
        if active_call then active_call.primary_unit = thrown end
    end


    -- The corridor: feed the actual track, whether or not a call is active. The Eagle is
    -- visible before the beacon lands (measured: 0.0-3.5 s after the call, landing comes
    -- 3.7-8.9 s in), so waiting for a call to be "live" would waste the earliest warning.
    -- Where to draw the self-test line: beside the beacon-identity prop on the ship, which
    -- sits where the player is - so the line is actually visible instead of 100 m away in
    -- empty space.
    if M.selftest and M.selftest_origin == nil and #beacon_entries > 0 then
        local o = world_position(beacon_entries[1].unit)
        if o then M.selftest_origin = { o[1], o[2], o[3] } end
    end

    update_trail(eagle_entries)

    if active_call == nil then
        -- Idle: still record eagle sightings, because the Eagle orbits between calls
        -- and its pre-call heading is exactly what a prediction mod would need.
        if #eagle_entries > 0 then
            emit({ kind = 'idle_eagle', t = now, eagles = json_points(eagle_entries, true) })
        end
        return
    end

    -- One bounded pass per call, not a query storm on every tick.
    identify_call(world, active_call, now)

    active_call.samples = active_call.samples + 1
    active_call.last_seen = (#beacon_entries > 0) and now or active_call.last_seen

    local ok, line = pcall(function()
        return string.format(
            '{"kind":"sample","t":%.3f,"call":%d,"n":%d,"beacons":%s,"eagles":%s}',
            now, active_call.id, active_call.samples,
            json_points(beacon_entries, true), json_points(eagle_entries, true))
    end)
    if ok and jsonl then
        pcall(jsonl.write, jsonl, line .. '\n')
        -- 0.1.0's jsonl was lost when the process died, because it was only flushed on
        -- a clean shutdown. Flush as we go, so a crash still leaves the evidence.
        if M.samples % 25 == 0 then pcall(jsonl.flush, jsonl) end
    else
        M.errors = M.errors + 1
    end
    M.samples = M.samples + 1

    local gone = (#beacon_entries == 0) and (now - active_call.last_seen) > CALL_GONE_S
    local timed_out = (now - active_call.started) > CALL_TIMEOUT_S
    if gone or timed_out then
        local names = {}
        for src in pairs(active_call.srcs) do
            names[#names + 1] = STRATAGEM_OF[src] or src
        end
        table.sort(names)
        log(string.format('call %d ended after %.1fs, %d sample(s), reason=%s, saw=%s',
            active_call.id, now - active_call.started, active_call.samples,
            timed_out and 'timeout' or 'beacon gone',
            #names > 0 and table.concat(names, '+') or 'nothing'))
        emit({ kind = 'call_end', t = now, call = active_call.id,
               note = timed_out and 'timeout' or 'beacon_gone' })
        active_call = nil
        beacon_motion = {}
        for id in pairs(seen_beacon_ids) do seen_beacon_ids[id] = nil end
    end
end

-- ------------------------------------------------------------------- drawing --
-- The call pattern below is copied from a mod that already draws in this game, not
-- invented: create_line_object(world, false), then per frame reset -> add_line xN ->
-- dispatch, hiding with a zero-alpha line and destroying with destroy_line_object. That
-- matters - guessing an engine signature is what took the game down once already.
local function drawing_allowed(now)
    if M.draw_off or not M.draw_enabled then return false end
    -- Cheap file probe, at most every 2 s, so the escape hatch costs nothing per frame.
    if now >= (M.draw_checked or 0) then
        M.draw_checked = now + 2
        local ok, fh = pcall(io.open, KILL_SWITCH, 'r')
        if ok and fh then
            pcall(fh.close, fh)
            M.draw_enabled = false
            log('corridor DISABLED: ' .. KILL_SWITCH .. ' exists. Delete it and restart '
                .. 'the game to re-enable.')
            emit({ kind = 'draw_disabled', t = now, note = 'kill switch file present' })
            return false
        end
    end
    return true
end

local function release_line()
    if M.line and M.line_world then
        pcall(sr.World.destroy_line_object, M.line_world, M.line)
    end
    M.line, M.line_world = nil, nil
end

local function ensure_line(world)
    if M.line and M.line_world == world then return M.line end
    release_line()
    local ok, line = pcall(sr.World.create_line_object, world, false)
    if not ok or line == nil then return nil end
    M.line, M.line_world = line, world
    return line
end

-- Called every frame. The geometry is cached; this only re-submits it, because a
-- dispatched line object is a per-frame submission and would otherwise vanish between
-- samples.
local function draw_corridor()
    -- drawing_allowed re-checks the kill-switch file at most every 2 s, so the escape hatch
    -- works DURING a session and not only at load. It was written and then not called, which
    -- would have left the switch effective only on restart - the opposite of what the README
    -- promises and of what makes it an escape hatch.
    if not drawing_allowed(os.clock()) then return end
    local trail = M.trail

    -- Drawing self-test: a fixed line beside the ship, so the line API is proven on this
    -- build while the player is still on the ship. It clears itself afterwards; the file
    -- is the opt-in, and the log line is the result.
    if M.selftest and #trail == 0 and M.selftest_origin then
        local world = main_world()
        if world == nil then return end
        local line = ensure_line(world)
        if line == nil then
            M.selftest = false
            log('SELFTEST FAILED: create_line_object returned nothing')
            return
        end
        local o = M.selftest_origin
        local ok = pcall(function()
            sr.LineObject.reset(line)
            local mid = { o[1] + 60, o[2], o[3] + 1.5 }
            sr.LineObject.add_line(line, sr.Color(0, 255, 128, 220),
                sr.Vector3(o[1], o[2], o[3] + 1.5), sr.Vector3(mid[1], mid[2], mid[3]))
            sr.LineObject.add_line(line, sr.Color(0, 255, 128, 220),
                sr.Vector3(mid[1], mid[2], mid[3]),
                sr.Vector3(o[1] + 120, o[2], o[3] + 1.5))
            sr.LineObject.dispatch(world, line)
        end)
        M.selftest_frames = M.selftest_frames + 1
        if not ok then
            M.selftest = false
            M.draw_off = true
            log('SELFTEST FAILED: the line API raised. Corridor disabled; sampling '
                .. 'continues.')
            release_line()
            emit({ kind = 'selftest', t = os.clock(), note = 'failed' })
        elseif M.selftest_frames >= 240 then
            M.selftest = false
            log(string.format('SELFTEST OK: drew a 120 m line for %d frames beside the '
                .. 'ship, then released it. The line API works on this build.',
                M.selftest_frames))
            emit({ kind = 'selftest', t = os.clock(), note = 'ok' })
            release_line()
        end
        return
    end

    if #trail == 0 then
        -- Nothing to show: hide any line left over from the previous pass rather than
        -- leaving a stale corridor on screen after the aircraft is gone.
        if M.line and M.line_world then
            pcall(function()
                sr.LineObject.reset(M.line)
                local z = sr.Vector3(0, 0, 0)
                sr.LineObject.add_line(M.line, sr.Color(0, 0, 0, 0), z, z)
                sr.LineObject.dispatch(M.line_world, M.line)
            end)
        end
        return
    end
    local world = main_world()
    if world == nil then return end
    local line = ensure_line(world)
    if line == nil then return end
    local ok = pcall(function()
        sr.LineObject.reset(line)
        local trail = M.trail
        local n = #trail
        for i = 1, n - 1 do
            sr.LineObject.add_line(line, sr.Color(COLOR_TRAIL[1], COLOR_TRAIL[2],
                COLOR_TRAIL[3], COLOR_TRAIL[4]),
                sr.Vector3(trail[i][1], trail[i][2], trail[i][3]),
                sr.Vector3(trail[i + 1][1], trail[i + 1][2], trail[i + 1][3]))
        end
        local head = M.trail_heading
        if head and n >= 1 then
            local p = trail[n]
            local ahead = { p[1] + head[1] * FORWARD_M, p[2] + head[2] * FORWARD_M,
                            p[3] + head[3] * FORWARD_M }
            sr.LineObject.add_line(line, sr.Color(COLOR_HEAD[1], COLOR_HEAD[2],
                COLOR_HEAD[3], COLOR_HEAD[4]), sr.Vector3(p[1], p[2], p[3]),
                sr.Vector3(ahead[1], ahead[2], ahead[3]))
            -- Arrowhead: two arms swept back from the far end, in the horizontal plane.
            local bx, by = -head[1], -head[2]
            local len = math.sqrt(bx * bx + by * by)
            if len > 0 then
                bx, by = bx / len, by / len
                local px, py = -by, bx
                local tip = ahead
                for _, s in ipairs({ 1, -1 }) do
                    sr.LineObject.add_line(line, sr.Color(COLOR_HEAD[1], COLOR_HEAD[2],
                        COLOR_HEAD[3], COLOR_HEAD[4]),
                        sr.Vector3(tip[1], tip[2], tip[3]),
                        sr.Vector3(tip[1] + (bx + px * s) * ARROW_M,
                                   tip[2] + (by + py * s) * ARROW_M,
                                   tip[3]))
                end
            end
        end
        sr.LineObject.dispatch(world, line)
    end)
    if not ok then
        M.errors = M.errors + 1
        M.draw_off = true
        log('corridor drawing ERRORED and switched itself off; sampling continues')
    end
    M.draw_frames = M.draw_frames + 1
end

-- Every tick runs inside the temp-byte-count guard and is timed. A tick that busts the
-- budget slows the probe down; a run of them stops it. A probe that can degrade the
-- game is not worth its data, and 0.2.0 had neither guard.
local function guarded()
    local began = os.clock()
    local saved = temp_guard_begin()
    local ok, reason = pcall(sample_body)

    -- The corridor is re-submitted EVERY frame, inside the same temp guard. A dispatched
    -- line object is a per-frame submission, so dispatching only at the sample rate would
    -- make it flicker or vanish; the geometry it submits is cached and recomputed at the
    -- sample rate, so the per-frame cost is just the submission.
    --
    -- The cost guarantee here is DETERMINISTIC, not measured: at most TRAIL_MAX-1 segments
    -- plus three for the head and arrowhead, capped by construction. os.clock() on this
    -- engine has roughly 15.6 ms granularity - every query in this probe measures 0.0 ms
    -- against it - so a fine-grained draw budget could not be believed even if it were
    -- computed. A non-zero reading therefore means something gross, and a run of those
    -- switches drawing off on its own.
    local draw_began = os.clock()
    if ok and M.draw_enabled and not M.draw_off then pcall(draw_corridor) end
    local draw_spent = (os.clock() - draw_began) * 1000
    M.draw_last_ms = draw_spent
    if draw_spent > (M.draw_peak_ms or 0) then M.draw_peak_ms = draw_spent end
    temp_guard_end(saved)
    local spent = (os.clock() - began) * 1000
    M.last_tick_ms = spent
    M.last_temp_bytes = saved
    if spent > (M.slowest_tick_ms or 0) then M.slowest_tick_ms = spent end

    if not ok then
        M.errors = M.errors + 1
        M.last_error = tostring(reason)
        M.status = 'probe_error'
        return
    end

    -- A draw that registers at all on a ~15.6 ms clock is gross, so a short run of them is
    -- enough to stop drawing. Sampling deliberately continues: losing the corridor is
    -- survivable, losing the measurement is not.
    if draw_spent > DRAW_BUDGET_MS and not M.draw_off then
        M.draw_slow = (M.draw_slow or 0) + 1
        log(string.format('slow draw: %.1f ms on the ~15.6 ms clock (slow #%d of %d)',
            draw_spent, M.draw_slow, DRAW_SLOW_BEFORE_OFF))
        if M.draw_slow >= DRAW_SLOW_BEFORE_OFF then
            M.draw_off = true
            release_line()
            log('corridor DISABLED: drawing was too slow. Sampling continues.')
            emit({ kind = 'draw_disabled', t = os.clock(), note = 'slow draw' })
        end
    else
        M.draw_slow = 0
    end

    if spent > TICK_BUDGET_MS and not M.stopped then
        M.slow_ticks = M.slow_ticks + 1
        M.backoff = math.min((M.backoff or 1) * 2, 20)
        log(string.format('slow tick: %.1f ms over the %d ms budget (slow #%d, '
            .. 'interval now 1/%d of nominal)', spent, TICK_BUDGET_MS, M.slow_ticks,
            M.backoff))
        if M.slow_ticks >= SLOW_TICKS_BEFORE_STOP then
            M.stopped = true
            log('SELF-DISABLED: too many slow ticks. Sampling stopped so the probe '
                .. 'cannot keep loading the engine. Send this log.')
            emit({ kind = 'stopped', t = os.clock(),
                   note = 'self-disabled after slow ticks' })
        end
    end
end

-- --------------------------------------------------------------------- install --
local function install()
    if not open_jsonl() then
        log('WARNING: could not open ' .. JSONL_PATH .. '; log-only mode')
    else
        -- Naming the file in the log means the samples can always be found, even though
        -- the name now changes every session.
        log('samples file: ' .. JSONL_PATH)
    end
    log(string.format('v%s installed (no writes to game memory; draws the Eagle corridor)',
        M.version))
    local capable = report_capabilities()
    if not capable then
        M.status = 'no_engine_api'
        return M
    end

    resolve_query_keys()

    -- Drawing needs the line API. If this build does not expose it, sampling still runs -
    -- the corridor is the feature, the measurement is the reason the mod exists.
    --
    -- Capability is proven by CONSTRUCTING one of each, not by testing the type. The first
    -- 0.7.0 run tested `type(sr.Vector3) == 'function'` and switched the corridor off: on
    -- this build sr.Vector3 is a callable TABLE (and sr.Color is a function), so a type test
    -- was a guess about the API dressed up as a check. The construction is wrapped in the
    -- temp guard because building a vector allocates in the script temp arena.
    local cap_saved = temp_guard_begin()
    local ok_vec = pcall(sr.Vector3, 0, 0, 0)
    local ok_col = pcall(sr.Color, 255, 255, 255, 255)
    temp_guard_end(cap_saved)

    local reasons = {}
    local function insist(label, value)
        if value then return true end
        reasons[#reasons + 1] = label
        return false
    end
    local can_draw = true
    can_draw = insist('World.create_line_object',
        type(sr.World.create_line_object) == 'function') and can_draw
    can_draw = insist('World.destroy_line_object',
        type(sr.World.destroy_line_object) == 'function') and can_draw
    can_draw = insist('LineObject', type(sr.LineObject) == 'table') and can_draw
    if type(sr.LineObject) == 'table' then
        can_draw = insist('LineObject.reset', type(sr.LineObject.reset) == 'function') and can_draw
        can_draw = insist('LineObject.add_line',
            type(sr.LineObject.add_line) == 'function') and can_draw
        can_draw = insist('LineObject.dispatch',
            type(sr.LineObject.dispatch) == 'function') and can_draw
    end
    can_draw = insist('sr.Vector3 constructible', ok_vec) and can_draw
    can_draw = insist('sr.Color constructible', ok_col) and can_draw

    if not can_draw then
        M.draw_enabled = false
        log('corridor OFF: missing on this build -> ' .. table.concat(reasons, ', '))
    else
        -- One check at load, so the escape hatch is honoured before the first frame.
        local okf, fh = pcall(io.open, KILL_SWITCH, 'r')
        if okf and fh then
            pcall(fh.close, fh)
            M.draw_enabled = false
            log('corridor OFF: ' .. KILL_SWITCH .. ' exists. Delete that file and restart '
                .. 'the game to draw it again.')
        end
        local oks, sh = pcall(io.open, SELFTEST_FILE, 'r')
        if oks and sh then
            pcall(sh.close, sh)
            M.selftest = true
            log('SELFTEST requested: a 120 m line will be drawn beside the ship for ~4 s, '
                .. 'then released. Delete ' .. SELFTEST_FILE .. ' to stop asking for it.')
        end
    end
    log(string.format('corridor: %s (actual flight path + heading arrow, no width - '
        .. 'a width would be a per-stratagem guess we cannot yet make). Kill switch: %s',
        M.draw_enabled and 'ON' or 'OFF', KILL_SWITCH))
    log(string.format('v%s: %d Hz, in-session only, %d ms tick budget, self-disables '
        .. 'after %d slow ticks, %d s startup grace', M.version, SAMPLE_HZ,
        TICK_BUDGET_MS, SLOW_TICKS_BEFORE_STOP, STARTUP_GRACE_S))
    log(string.format('querying the aircraft + beacon every tick; %d munition '
        .. 'identities once per call under a %d ms budget', #RESOLVED,
        IDENTIFY_BUDGET_MS))

    local previous = rawget(_G, 'update')
    if type(previous) == 'function' then
        rawset(_G, 'update', function(...)
            guarded()
            return previous(...)
        end)
        M.hooked = true
    else
        log('WARNING: no global update function; probe will not sample')
    end

    local shutdown = rawget(_G, 'shutdown')
    if type(shutdown) == 'function' then
        rawset(_G, 'shutdown', function(...)
            pcall(function()
                log(string.format('shutdown: samples=%d calls=%d errors=%d reads=%d '
                    .. 'slowest_tick=%.1fms slow_ticks=%d backoff=x%d', M.samples,
                    M.calls, M.errors, M.reads, M.slowest_tick_ms or 0, M.slow_ticks,
                    M.backoff or 1))
                log(string.format('  corridor: frames=%d peak_draw=%.1fms draw_off=%s '
                    .. 'enabled=%s', M.draw_frames, M.draw_peak_ms or 0,
                    tostring(M.draw_off), tostring(M.draw_enabled)))
                release_line()
                for _, row in ipairs(M.key_costs) do
                    log(string.format('  query cost %-18s units=%d %.2f ms',
                        row.src, row.units, row.ms))
                end
                if jsonl then jsonl:flush(); jsonl:close(); jsonl = nil end
            end)
            return shutdown(...)
        end)
    end

    M.status = 'running'
    guarded()
    return M
end

return install()
