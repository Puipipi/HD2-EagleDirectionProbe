-- HD2-Addon: mods/codex/eagle_performance_clock
-- Optional high-resolution wall clock for measuring Lua/native wrapper paths.
-- This module reads no game memory and uses no HD2Runtime API.
local P = {}

local function finite(value)
    return type(value) == 'number' and value == value
        and value ~= math.huge and value ~= -math.huge
end

local function fallback_clock(options)
    local read = options.fallback_now
    if type(read) ~= 'function' then
        read = function() return os.clock() * 1000 end
    end
    local source = options.fallback_source or 'fallback-os.clock'
    local resolution = options.fallback_resolution_ms
    if not finite(resolution) or resolution <= 0 then resolution = 15.6 end
    return read, source, resolution
end

function P.new(options)
    options = type(options) == 'table' and options or {}
    local read_fallback, fallback_source, fallback_resolution = fallback_clock(options)
    local clock = {
        source = 'fallback-not-initialized',
        precise = false,
        resolution_ms = fallback_resolution,
    }

    local initialized, counter, frequency, origin, qpc = false, nil, nil, nil, nil
    local last_ms, fallback_offset, fallback_origin = nil, nil, nil

    local function fallback_value()
        local ok, value = pcall(read_fallback)
        if not ok or not finite(value) then return nil end
        return value
    end

    local function begin_fallback(reason)
        local now = fallback_value()
        if now ~= nil then
            fallback_origin = now
            fallback_offset = last_ms or 0
        else
            fallback_origin = nil
            fallback_offset = last_ms or 0
        end
        clock.source = reason and ('fallback-' .. reason) or fallback_source
        clock.precise = false
        clock.resolution_ms = fallback_resolution
    end

    local function initialize_qpc()
        initialized = true
        local ok, result = pcall(function()
            local ffi = options.ffi
            if ffi == nil then ffi = require('ffi') end
            assert(type(ffi) == 'table' and ffi.os == 'Windows', 'Windows LuaJIT required')
            assert(type(ffi.cdef) == 'function' and type(ffi.new) == 'function'
                and type(ffi.load) == 'function', 'LuaJIT FFI unavailable')
            ffi.cdef[[
                int __stdcall QueryPerformanceCounter(long long *lpPerformanceCount);
                int __stdcall QueryPerformanceFrequency(long long *lpFrequency);
            ]]
            local kernel = ffi.load('kernel32')
            local frequency_buffer = ffi.new('long long[1]')
            local counter_buffer = ffi.new('long long[1]')
            local qpf_ok = kernel.QueryPerformanceFrequency(frequency_buffer)
            local hz = tonumber(frequency_buffer[0])
            assert(qpf_ok ~= 0 and qpf_ok ~= false and qpf_ok ~= nil
                and finite(hz) and hz > 0, 'QPC frequency unavailable')
            local qpc_ok = kernel.QueryPerformanceCounter(counter_buffer)
            assert(qpc_ok ~= 0 and qpc_ok ~= false and qpc_ok ~= nil,
                'QPC counter unavailable')
            return {
                counter = counter_buffer,
                frequency = hz,
                origin = ffi.new('long long', counter_buffer[0]),
                qpc = function(buffer) return kernel.QueryPerformanceCounter(buffer) end,
            }
        end)
        if ok and type(result) == 'table' then
            counter, frequency, origin, qpc = result.counter, result.frequency,
                result.origin, result.qpc
            clock.source = 'qpc'
            clock.precise = true
            clock.resolution_ms = 1000 / frequency
            last_ms = 0
            return
        end
        begin_fallback()
    end

    local function fallback_now()
        local value = fallback_value()
        if value ~= nil then
            if fallback_origin == nil then
                fallback_origin = value
                fallback_offset = last_ms or 0
            end
            value = (fallback_offset or 0) + (value - fallback_origin)
            if last_ms == nil or value > last_ms then last_ms = value end
        end
        return last_ms or 0
    end

    function clock.now_ms()
        if not initialized then
            initialize_qpc()
            if counter ~= nil then return last_ms or 0 end
        end
        if counter ~= nil then
            local ok, value = pcall(qpc, counter)
            if ok and value ~= 0 and value ~= false and value ~= nil then
                local milliseconds = tonumber(counter[0] - origin) * 1000 / frequency
                if finite(milliseconds) and milliseconds >= 0
                    and (last_ms == nil or milliseconds >= last_ms) then
                    last_ms = milliseconds
                    return last_ms
                end
            end
            counter = nil
            begin_fallback('qpc-error')
        end
        return fallback_now()
    end

    return clock
end

return P
