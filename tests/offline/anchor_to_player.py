"""Anchor to the player's own avatar, using the calls a proven mod already uses.

Two problems solved at once.

1. THE SHIP SELF-TEST WAS ANCHORED TO A DECORATIVE PROP whose position relative to the player I
   could not know, so "nothing on the ship" proved nothing about rendering. The geometry box also
   showed the ribbon was 41 m wide instead of sub-metre, which gave the game away: M.anchor was a
   leftover from an earlier mission ~9 km away, so the strands fanned out.

2. THE WIDTH ANCHOR IS MEANT TO BE THE CAMERA, and this probe has no FFI, so it has been guessing.
   The player's own unit is a far better proxy than a stale mission position.

The avatar is found exactly as HUD_Ballistic_Trajectory_Overlay does it - units_by_resource on the
third-person avatar, alive(), and the animation state machine's player_number when several rigs
exist. No new API is invented here; every call is copied from a mod that runs.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
src = ROOT / "mods" / "eagle-direction-probe" / "src" / "eagle_direction_probe.lua"
t = src.read_text(encoding="utf-8")
before = t

HELPER = '''
-- The local player's unit, resolved with the calls HUD_Ballistic_Trajectory_Overlay uses: the
-- third-person avatar by resource, alive(), and player_number from its animation state machine
-- when more than one rig is present. No FFI, and no invented API.
--
-- This matters twice over. It is the honest stand-in for the camera position, which the width
-- scaling needs; and on the ship it is the one point guaranteed to be in front of the player, so
-- the drawing self-test can be anchored somewhere that "I cannot see it" actually means something.
local AVATAR_TP = 'content/fac_helldivers/cha_avatar/avatar_helldiver'

local function unit_player_number(unit)
    local u = sr.Unit
    if type(u.has_animation_state_machine) ~= 'function'
        or type(u.animation_has_variable) ~= 'function'
        or type(u.animation_find_variable) ~= 'function'
        or type(u.animation_get_variable) ~= 'function' then
        return nil
    end
    local ok1, has = pcall(u.has_animation_state_machine, unit)
    if not ok1 or has ~= true then return nil end
    local ok2, found = pcall(u.animation_has_variable, unit, 'player_number')
    if not ok2 or found ~= true then return nil end
    local ok3, id = pcall(u.animation_find_variable, unit, 'player_number')
    if not ok3 or id == nil then return nil end
    local ok4, value = pcall(u.animation_get_variable, unit, id)
    if not ok4 then return nil end
    return value
end

local function local_player(world)
    if world == nil then return nil end
    local ok, units = pcall(units_by_resource, world, AVATAR_TP)
    if not ok or type(units) ~= 'table' then return nil end
    local single = nil
    for _, unit in ipairs(as_list(units)) do
        local alive_ok, alive = pcall(sr.Unit.alive, unit)
        if alive_ok and alive == true then
            if single == nil then
                single = unit
            else
                -- More than one rig: keep only the one whose player_number matches the first.
                local want = unit_player_number(single)
                if want ~= nil and unit_player_number(unit) == want then
                    -- still ambiguous, so refuse rather than guess
                    return nil
                end
            end
        end
    end
    return single
end

local function player_position(world)
    local unit = local_player(world)
    if unit == nil then return nil end
    return world_position(unit)
end

'''

anchor = "local function build_geometry()"
if anchor not in t:
    print("MISSING ANCHOR: build_geometry")
else:
    t = t.replace(anchor, HELPER + anchor, 1)

# Width anchor: the player when nothing better is known. The old value could be a stale mission
# position, which fanned the ribbons out to 41 m.
t = t.replace(
    "    M.anchor = M.impact or trail[n] or M.anchor",
    """    -- The player's own position is the honest proxy for the camera; a stale value from an earlier
    -- mission is not. M.anchor is reassigned every rebuild so it cannot drift like that again.
    M.anchor = nil
    for _, imp in pairs(M.impacts) do M.anchor = M.anchor or imp.p end
    for _, track in pairs(M.tracks) do M.anchor = M.anchor or track.trail[#track.trail] end
    if M.anchor == nil and M.anchor_player ~= nil then M.anchor = M.anchor_player end""")

# On the ship the self-test anchors to the player, not to a prop of unknown position.
t = t.replace(
    """    if M.selftest and next(M.tracks) == nil and M.selftest_origin then
        local world = main_world()
        if world == nil then return end""",
    """    if M.selftest and next(M.tracks) == nil then
        local world = main_world()
        if world == nil then return end
        -- Anchor where the player is standing, refreshed every rebuild: the whole point of the
        -- ship test is to draw something the player cannot fail to be looking at.
        local ppos = player_position(world)
        if ppos ~= nil then
            M.anchor_player = ppos
            M.selftest_origin = { ppos[1], ppos[2], ppos[3] }
            M.selftest_seg = nil
        end
        if M.selftest_origin == nil then return end""")

src.write_text(t, encoding="utf-8")
print("changed" if t != before else "NOTHING CHANGED")
for probe in ("AVATAR_TP", "local function local_player(", "player_position(world)",
              "M.anchor = nil", "M.anchor_player"):
    print("  %-32s %s" % (probe, "ok" if probe in t else "MISSING"))
