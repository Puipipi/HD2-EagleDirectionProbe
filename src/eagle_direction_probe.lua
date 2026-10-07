-- HD2-Addon: mods/codex/eagle_direction_probe
-- Eagle Direction Probe -- READ-ONLY measurement addon.
--
-- ONE QUESTION, ONE MISSION: when an Eagle-series red stratagem is called, what is
-- the Eagle aircraft's ACTUAL incoming direction, and how does it relate to the
-- player and to the stratagem beacon?
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
    version = '0.1.0',
    status = 'starting',
    reads = 0,
    errors = 0,
    samples = 0,
    calls = 0,
    stopped = false,
}
rawset(_G, MOD_KEY, M)

-- ------------------------------------------------------------------ constants --
-- Discovered offline from a 16 GB full process dump (2026-10-05 build) and from
-- the installed mods' own source. Both keys below are evidence-backed, not guesses.
local EAGLE_RESOURCE = 'content/fac_helldivers/vehicles/eagle/eagle'
local BEACON_HEX = '16f397ca5f51f271'   -- HUD_BTO catalog: {name="Beacon", resource_hex=...}

-- Entity GUIDs that the kill-feed / damage tables name as Eagle things. Used only by
-- the optional fallback scan, to recognise a unit without knowing its path.
local EAGLE_GUIDS = {
    ['0bd0f9d59048e9d1'] = 'eagle_gunpods',
    ['1b3bcadabc7ef8d6'] = 'eagle_airstrike_smoke',
    ['23a60681dd4383ec'] = 'eagle_base',
    ['27bb558c893383cc'] = 'eagle_napalm',
    ['2ea01cb1676aca29'] = 'eagle_airstrike',
    ['397792815583da29'] = 'eagle_rocket',
    ['dfbb9a0d8fa27d85'] = 'eagle_missile',
    ['e44b691dc039a505'] = 'eagle_bomb',
}

local SAMPLE_HZ = 10            -- engine accessor calls per second
local MAX_SAMPLES = 20000       -- hard stop; keeps the log bounded
local CALL_TIMEOUT_S = 30       -- a call is abandoned after this long
local CALL_GONE_S = 3           -- ...or this long after the beacon disappears

-- Off by default. Turning this on makes the probe walk the whole world (about 22,000
-- units on a mission world) to find Eagle units by identity. That path has a crash
-- precedent in this workspace, so it is chunked and only runs while a call is live.
local FALLBACK_WORLD_SCAN = false
local SCAN_CHUNK = 2000

-- ---------------------------------------------------------------------- paths --
local HOME = (os.getenv('LOCALAPPDATA') or os.getenv('TEMP') or '.')
    .. '/CowboyBingus/Helldivers2'
local LOG_PATH = HOME .. '/Logs/EagleDirectionProbe.log'
local JSONL_PATH = HOME .. '/Logs/EagleDirectionProbe.jsonl'

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

local function emit(record)
    if not jsonl or M.stopped then return end
    local ok, line = pcall(function()
        local parts = {}
        for _, key in ipairs({ 'kind', 't', 'call', 'note' }) do
            if record[key] ~= nil then
                parts[#parts + 1] = string.format('%q:%s', key,
                    type(record[key]) == 'string' and string.format('%q', record[key])
                    or tostring(record[key]))
            end
        end
        for _, key in ipairs({ 'beacons', 'eagles', 'caps', 'ids' }) do
            local value = record[key]
            if value ~= nil then
                parts[#parts + 1] = string.format('%q:%s', key, value)
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
                    'Color', 'Camera', 'LineObject', 'Gui' }
    local caps, missing = {}, {}
    for _, name in ipairs(names) do
        caps[name] = type(sr[name])
        if type(sr[name]) ~= 'table' then missing[#missing + 1] = name end
    end
    local need = { 'Application', 'World', 'Unit', 'Vector3' }
    local ok = true
    for _, name in ipairs(need) do
        if type(sr[name]) ~= 'table' then ok = false end
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

local function beacon_key()
    if type(sr.IdString64) == 'table' and sr.IdString64.from_hex then
        local ok, key = pcall(sr.IdString64.from_hex, BEACON_HEX)
        if ok and key ~= nil then return key end
    end
    return BEACON_HEX      -- some builds accept the plain path/hex string
end

-- ------------------------------------------------------------------ call state --
local next_sample = 0
local active_call = nil
local seen_beacon_ids = {}
local call_serial = 0

local function json_points(units, want_pose)
    local out = {}
    for _, unit in ipairs(units) do
        local p = world_position(unit)
        if p then
            local row = string.format('{"id":%q,"p":[%.4f,%.4f,%.4f]',
                unit_identity(unit) or '?', p[1], p[2], p[3])
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
            row = row .. (want_pose and ',"pose":true' or '') .. '}'
            out[#out + 1] = row
        end
    end
    return '[' .. table.concat(out, ',') .. ']'
end

local function begin_call(now, beacons)
    call_serial = call_serial + 1
    active_call = {
        id = call_serial,
        started = now,
        last_seen = now,
        beacon_ids = {},
        samples = 0,
    }
    for _, unit in ipairs(beacons) do
        local id = unit_identity(unit)
        if id then
            active_call.beacon_ids[id] = true
            seen_beacon_ids[id] = now
        end
    end
    M.calls = M.calls + 1
    log(string.format('call %d began (beacon units=%d)', call_serial, #beacons))
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
        if id and (EAGLE_GUIDS[id] or id == BEACON_HEX) then
            found[#found + 1] = unit
        end
    end
    scan_cursor = last >= #scan_units.list and 0 or last
    return found
end

-- ----------------------------------------------------------------------- tick --
local function tick()
    if M.stopped then return end
    local now = os.clock()
    if now < next_sample then return end
    next_sample = now + (1 / SAMPLE_HZ)

    if M.samples >= MAX_SAMPLES then
        M.stopped = true
        log(string.format('stopped at the sample budget (%d)', MAX_SAMPLES))
        emit({ kind = 'stopped', t = now, note = 'sample budget' })
        return
    end

    local world = main_world()
    if world == nil then return end

    local beacons = units_by_resource(world, beacon_key())
    local eagles = units_by_resource(world, EAGLE_RESOURCE)
    if FALLBACK_WORLD_SCAN then
        for _, unit in ipairs(fallback_eagles(world, now)) do
            local duplicate = false
            for _, existing in ipairs(eagles) do
                if existing == unit then duplicate = true break end
            end
            if not duplicate then eagles[#eagles + 1] = unit end
        end
    end

    -- A call starts the first time we see a beacon we have not seen before.
    local fresh = false
    for _, unit in ipairs(beacons) do
        local id = unit_identity(unit)
        if id and seen_beacon_ids[id] == nil then fresh = true end
    end
    if fresh or (active_call == nil and #beacons > 0) then
        if active_call == nil then begin_call(now, beacons) end
    end

    if active_call == nil then
        -- Idle: still record eagle sightings, because the Eagle orbits between calls
        -- and its pre-call heading is exactly what a prediction mod would need.
        if #eagles > 0 then
            emit({ kind = 'idle_eagle', t = now, eagles = json_points(eagles, true) })
        end
        return
    end

    active_call.samples = active_call.samples + 1
    active_call.last_seen = (#beacons > 0) and now or active_call.last_seen

    local ok, line = pcall(function()
        return string.format(
            '{"kind":"sample","t":%.3f,"call":%d,"n":%d,"beacons":%s,"eagles":%s}',
            now, active_call.id, active_call.samples,
            json_points(beacons, true), json_points(eagles, true))
    end)
    if ok and jsonl then
        pcall(jsonl.write, jsonl, line .. '\n')
    else
        M.errors = M.errors + 1
    end
    M.samples = M.samples + 1

    local gone = (#beacons == 0) and (now - active_call.last_seen) > CALL_GONE_S
    local timed_out = (now - active_call.started) > CALL_TIMEOUT_S
    if gone or timed_out then
        log(string.format('call %d ended after %.1fs, %d sample(s), reason=%s',
            active_call.id, now - active_call.started, active_call.samples,
            timed_out and 'timeout' or 'beacon gone'))
        emit({ kind = 'call_end', t = now, call = active_call.id,
               note = timed_out and 'timeout' or 'beacon_gone' })
        active_call = nil
        for id in pairs(seen_beacon_ids) do seen_beacon_ids[id] = nil end
    end
end

local function guarded()
    local ok, reason = pcall(tick)
    if not ok then
        M.errors = M.errors + 1
        M.last_error = tostring(reason)
        M.status = 'probe_error'
    end
end

-- --------------------------------------------------------------------- install --
local function install()
    if not open_jsonl() then
        log('WARNING: could not open ' .. JSONL_PATH .. '; log-only mode')
    end
    log(string.format('v%s installed (read-only probe; no writes to game memory)',
        M.version))
    local capable = report_capabilities()
    if not capable then
        M.status = 'no_engine_api'
        return M
    end

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
                log(string.format('shutdown: samples=%d calls=%d errors=%d reads=%d',
                    M.samples, M.calls, M.errors, M.reads))
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
