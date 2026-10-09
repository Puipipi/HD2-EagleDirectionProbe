-- HD2-Addon: mods/codex/eagle_local_player_pose
-- Resolve the local pose through peer-owned PlayerCall -> synchronized avatar.
-- This module deliberately performs reads only and has no Runtime dependency.
local M = {}

local POSITION_INTERVAL = 0.1
local IDENTITY_INTERVAL = 1.0
local PLAYER_CALL_TYPE = 'un6y1d'
local AVATAR_TYPE = 'gl7xl2w'
local PLAYER_INDEX_FIELD_ID = 'b03b8bce'
local INVALID_AVATAR_ID = 32767

local function callable(owner, name)
    return type(owner) == 'table' and type(owner[name]) == 'function'
end

local function invoke(owner, name, ...)
    if not callable(owner, name) then
        return false, nil, 'API_UNAVAILABLE:' .. name
    end
    local ok, value = pcall(owner[name], ...)
    if not ok then return false, nil, 'READ_FAILED:' .. name end
    return true, value
end

local function finite_number(value)
    return type(value) == 'number' and value == value and value > -math.huge and value < math.huge
end

local function clear_identity(state)
    state.session = nil
    state.peer = nil
    state.player_call = nil
    state.player_index = nil
    state.avatar_id = nil
    state.avatar = nil
    state.identity_retry_at = nil
    state.legacy_checked = nil
    state.legacy_status = nil
    state.direct_status = nil
    state.fail_closed = false
    state.position = nil
    state.source = nil
end

local function clear_all(state)
    clear_identity(state)
    state.world = nil
    state.position = nil
    state.source = nil
    state.last_sample_at = nil
end

local function clear_position(state)
    state.position = nil
    state.source = nil
end

local function owned_player(sr, session, peer)
    local ok, ids, err = invoke(sr.GameSession, 'objects_owned_by', session, peer)
    if not ok then return nil, err end
    if type(ids) ~= 'table' then return nil, 'PLAYER_CALL_UNAVAILABLE' end

    local found, count = nil, 0
    for _, id in pairs(ids) do
        local exists_ok, exists, exists_err = invoke(sr.GameSession, 'game_object_exists', session, id)
        if not exists_ok then return nil, exists_err end
        if exists then
            local type_ok, is_player, type_err = invoke(sr.GameSession, 'game_object_is_type', session, id, PLAYER_CALL_TYPE)
            if not type_ok then return nil, type_err end
            if is_player then
                count = count + 1
                found = id
            end
        end
    end
    if count == 0 then return nil, 'PLAYER_CALL_UNAVAILABLE' end
    if count ~= 1 then return nil, 'AMBIGUOUS_PLAYER_CALL' end
    return found
end

local function valid_game_object_id(id)
    return finite_number(id) and id >= 0 and id % 1 == 0 and id ~= INVALID_AVATAR_ID
end

local function synchronized_avatar(sr, session, player_call)
    local field_ok, avatar_id, field_err = invoke(sr.GameSession, 'game_object_field',
        session, player_call, 'baegche')
    if not field_ok then return nil, field_err, true end
    if not valid_game_object_id(avatar_id) then return nil, 'AVATAR_FIELD_UNAVAILABLE', true end

    local exists_ok, exists, exists_err = invoke(sr.GameSession, 'game_object_exists', session, avatar_id)
    if not exists_ok then return nil, exists_err, true end
    if exists ~= true then return nil, 'AVATAR_FIELD_UNAVAILABLE', true end

    local type_ok, is_avatar, type_err = invoke(sr.GameSession, 'game_object_is_type',
        session, avatar_id, AVATAR_TYPE)
    if not type_ok then return nil, type_err, false, true end
    if is_avatar ~= true then return nil, 'AVATAR_TYPE_MISMATCH', false, true end

    local state_ok, avatar_state, state_err = invoke(sr.GameSession, 'game_object_field',
        session, avatar_id, 'state')
    if not state_ok then return nil, state_err, false, true end
    if avatar_state ~= 0 then
        if avatar_state == nil then return nil, 'AVATAR_STATE_UNAVAILABLE', false, true end
        return nil, 'AVATAR_NOT_ALIVE', false, true
    end
    return avatar_id
end

local function player_index(sr, session, player_call)
    local ok, info, err = invoke(sr.Network, 'object_info', PLAYER_CALL_TYPE)
    if not ok then return nil, err end
    if type(info) ~= 'table' or type(info.fields) ~= 'table' then
        return nil, 'PLAYER_INDEX_FIELD_UNAVAILABLE'
    end
    local has_index_field = false
    for _, field in pairs(info.fields) do
        if type(field) == 'table' and field.id ~= nil then
            local id = tostring(field.id):lower():gsub('^0x', '')
            if id == PLAYER_INDEX_FIELD_ID then has_index_field = true; break end
        end
    end
    if not has_index_field then return nil, 'PLAYER_INDEX_FIELD_UNAVAILABLE' end

    local field_ok, index, field_err = invoke(sr.GameSession, 'game_object_field', session, player_call, 'index')
    if not field_ok then return nil, field_err end
    if not finite_number(index) or index < 0 or index % 1 ~= 0 then
        return nil, 'PLAYER_INDEX_UNAVAILABLE'
    end
    return index
end

local function find_avatar(sr, world, index, avatar_units)
    local ok, units = pcall(avatar_units, world)
    if not ok or type(units) ~= 'table' then return nil, 'AVATAR_ENUMERATION_UNAVAILABLE' end
    local found, count, seen = nil, 0, {}
    for _, unit in pairs(units) do
        if unit ~= nil and not seen[unit] then
            seen[unit] = true
            local alive_ok, alive, alive_err = invoke(sr.Unit, 'alive', unit)
            if not alive_ok then return nil, alive_err end
            if alive then
                local sm_ok, has_sm, sm_err = invoke(sr.Unit, 'has_animation_state_machine', unit)
                if not sm_ok then return nil, sm_err end
                if has_sm then
                    local has_ok, has_variable, has_err = invoke(sr.Unit, 'animation_has_variable', unit, 'player_number')
                    if not has_ok then return nil, has_err end
                    if has_variable then
                        local find_ok, variable, find_err = invoke(sr.Unit, 'animation_find_variable', unit, 'player_number')
                        if not find_ok then return nil, find_err end
                        local value_ok, player_number, value_err = invoke(sr.Unit, 'animation_get_variable', unit, variable)
                        if not value_ok then return nil, value_err end
                        if player_number == index then
                            count = count + 1
                            found = unit
                        end
                    end
                end
            end
        end
    end
    if count == 0 then return nil, 'AVATAR_UNAVAILABLE' end
    if count ~= 1 then return nil, 'AMBIGUOUS_AVATAR' end
    return found
end

local function copy_vector(sr, vector)
    if vector == nil then return nil, 'POSITION_UNAVAILABLE' end
    local x_ok, x, x_err = invoke(sr.Vector3, 'x', vector)
    if not x_ok then return nil, x_err end
    local y_ok, y, y_err = invoke(sr.Vector3, 'y', vector)
    if not y_ok then return nil, y_err end
    local z_ok, z, z_err = invoke(sr.Vector3, 'z', vector)
    if not z_ok then return nil, z_err end
    if not finite_number(x) or not finite_number(y) or not finite_number(z) then
        return nil, 'POSITION_INVALID'
    end
    return { x = x, y = y, z = z }
end

local function synchronized_position(sr, session, avatar_id)
    local ok, vector, err = invoke(sr.GameSession, 'game_object_field', session, avatar_id, 'position')
    if not ok then return nil, err end
    return copy_vector(sr, vector)
end

local function unit_position(sr, avatar)
    local ok, vector, err = invoke(sr.Unit, 'world_position', avatar, 1)
    if not ok then return nil, err end
    return copy_vector(sr, vector)
end

function M.new(sr, options)
    options = options or {}
    local avatar_units = options.avatar_units
    local state = {}
    local resolver = {}

    local function resolve_legacy_avatar(world)
        if state.avatar ~= nil then
            local alive_ok, alive, alive_err = invoke(sr.Unit, 'alive', state.avatar)
            if not alive_ok then return nil, alive_err end
            if alive then return state.avatar end
            state.avatar = nil
        end
        if state.legacy_checked then return nil, state.legacy_status end
        state.legacy_checked = true
        if type(avatar_units) ~= 'function' then
            state.legacy_status = 'API_UNAVAILABLE:avatar_units'
            return nil, state.legacy_status
        end
        if state.player_index == nil then
            local index, index_err = player_index(sr, state.session, state.player_call)
            if index == nil then state.legacy_status = index_err; return nil, index_err end
            state.player_index = index
        end
        local avatar, avatar_err = find_avatar(sr, world, state.player_index, avatar_units)
        if avatar == nil then state.legacy_status = avatar_err; return nil, avatar_err end
        state.avatar = avatar
        state.legacy_status = nil
        return avatar
    end

    function resolver:sample(world, now_seconds)
        if world == nil then
            clear_all(state)
            return nil, 'WORLD_UNAVAILABLE', nil
        end
        if not finite_number(now_seconds) then return nil, 'TIME_UNAVAILABLE', nil end
        if state.world ~= world then
            local last_sample_at = state.last_sample_at
            clear_all(state)
            state.world = world
            state.last_sample_at = last_sample_at
            state.status = 'WORLD_CHANGED'
        end
        if state.last_sample_at ~= nil and now_seconds >= state.last_sample_at and
            now_seconds - state.last_sample_at + 0.000000001 < POSITION_INTERVAL then
            if state.position then return state.position, state.status or 'OK', state.source end
            return nil, state.status or 'POSE_UNAVAILABLE', nil
        end
        state.last_sample_at = now_seconds

        local session_ok, session, session_err = invoke(sr.Network, 'game_session')
        if not session_ok then state.status = session_err; clear_position(state); return nil, session_err, nil end
        if session == nil then state.status = 'SESSION_UNAVAILABLE'; clear_position(state); return nil, state.status, nil end
        if not callable(sr.Network, 'peer_id') then
            state.status = 'API_UNAVAILABLE:Network.peer_id'; clear_position(state)
            return nil, state.status, nil
        end
        local peer_ok, peer, peer_err = invoke(sr.Network, 'peer_id')
        if not peer_ok then state.status = peer_err; clear_position(state); return nil, peer_err, nil end
        if peer == nil then state.status = 'PEER_UNAVAILABLE'; clear_position(state); return nil, state.status, nil end

        if state.session ~= session or state.peer ~= peer then
            clear_identity(state)
            state.session, state.peer = session, peer
        end

        if state.identity_retry_at == nil or now_seconds >= state.identity_retry_at then
            local player, player_err = owned_player(sr, session, peer)
            if player == nil then
                clear_identity(state)
                state.session, state.peer = session, peer
                state.identity_retry_at = now_seconds + IDENTITY_INTERVAL
                state.status = player_err; clear_position(state)
                return nil, player_err, nil
            end
            if state.player_call ~= player then
                state.player_index, state.avatar_id, state.avatar = nil, nil, nil
                clear_position(state)
            end
            state.player_call = player
            state.identity_retry_at = now_seconds + IDENTITY_INTERVAL
            state.legacy_checked, state.legacy_status = false, nil

            state.fail_closed = false
            local avatar_id, avatar_err, avatar_fallback, fail_closed = synchronized_avatar(sr, session, player)
            if fail_closed then
                state.avatar_id, state.avatar = nil, nil
                state.direct_status, state.legacy_status = avatar_err, nil
                state.fail_closed = true
                clear_position(state)
                state.status = avatar_err
                return nil, avatar_err, nil
            end
            if avatar_id ~= state.avatar_id then
                clear_position(state)
                state.avatar = nil
            end
            state.avatar_id = avatar_id
            state.direct_status = avatar_err
            if avatar_id == nil and avatar_fallback then
                local index, index_err = player_index(sr, session, player)
                if index ~= nil then state.player_index = index end
                local avatar, find_err
                if index ~= nil then avatar, find_err = find_avatar(sr, world, index, avatar_units)
                else find_err = index_err end
                state.legacy_checked = true
                if avatar ~= nil then
                    state.avatar, state.legacy_status = avatar, nil
                else
                    state.legacy_status = find_err
                end
            elseif avatar_id == nil then
                state.status = avatar_err
                clear_position(state)
                return nil, avatar_err, nil
            end
        elseif state.player_call == nil then
            clear_position(state)
            return nil, state.status or 'PLAYER_CALL_UNAVAILABLE', nil
        end

        if state.fail_closed then
            clear_position(state)
            return nil, state.status or state.direct_status or 'AVATAR_STATE_UNAVAILABLE', nil
        end

        if state.avatar_id ~= nil then
            local position, position_err = synchronized_position(sr, session, state.avatar_id)
            if position ~= nil then
                state.position, state.status, state.source = position, 'OK', 'network_avatar'
                return position, 'OK', state.source
            end
            local avatar, avatar_err = resolve_legacy_avatar(world)
            if avatar ~= nil then
                local fallback, fallback_err = unit_position(sr, avatar)
                if fallback ~= nil then
                    state.position, state.status, state.source = fallback, 'OK', 'animation_fallback'
                    return fallback, 'OK', state.source
                end
                avatar_err = fallback_err
            end
            state.status = position_err or avatar_err; clear_position(state)
            return nil, state.status, nil
        end

        if state.avatar ~= nil then
            local alive_ok, alive, alive_err = invoke(sr.Unit, 'alive', state.avatar)
            if not alive_ok then state.status = alive_err; clear_position(state); return nil, alive_err, nil end
            if not alive then state.avatar, state.legacy_checked = nil, false end
        end
        if state.avatar == nil and state.fail_closed then
            state.status = state.direct_status or 'AVATAR_STATE_UNAVAILABLE'; clear_position(state)
            return nil, state.status, nil
        end
        if state.avatar == nil then
            local avatar, avatar_err = resolve_legacy_avatar(world)
            if avatar == nil then
                local status = avatar_err or state.legacy_status or state.direct_status or 'AVATAR_UNAVAILABLE'
                state.status = status; clear_position(state)
                return nil, status, nil
            end
        end
        if state.avatar ~= nil then
            local position, position_err = unit_position(sr, state.avatar)
            if position ~= nil then
                state.position, state.status, state.source = position, 'OK', 'animation_fallback'
                return position, 'OK', state.source
            end
            state.status = position_err; clear_position(state)
            return nil, position_err, nil
        end

        local status = state.legacy_status or state.direct_status or 'AVATAR_UNAVAILABLE'
        state.status = status; clear_position(state)
        return nil, status, nil
    end

    return resolver
end

return M
