"""Stop holding engine Vector3 objects across frames.

THE BUG, found from the game itself. The same cached geometry logged as a valid box in the frame it
was built and as x 0..inf in every frame after:

  14:38:14  geometry box: 25 segments | x 7..127 (120 m) | y -28..13 (41 m) | z 22..22
  14:39:06  geometry box: 25 segments | x 0..inf (inf m)  | y 0..inf        | z 0..inf

The cause is this mod's own safety discipline: every frame ends with
sr.Script.set_temp_byte_count(saved), which RESTORES the script temp arena. Vector3 objects
allocated during a frame live in that arena, so restoring the count recycles them. Caching them for
later frames means submitting coordinates that point at reused memory - the geometry is built
correctly, dispatched successfully, and drawn from garbage. That is "nothing shows".

So the cache holds plain Lua numbers now, and the sr.Vector3 objects are constructed at submit
time, inside the same frame as the dispatch. Colour objects are built the same way for the same
reason.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
src = ROOT / "mods" / "eagle-direction-probe" / "src" / "eagle_direction_probe.lua"
t = src.read_text(encoding="utf-8")
before = t

# 1. add_ribbon stores plain {x,y,z} tables, never engine vectors.
t = t.replace(
    """local function add_ribbon(seg, ax, ay, az, bx, by, bz, strands, kind)
    local dx, dy = bx - ax, by - ay
    local len = math.sqrt(dx * dx + dy * dy)
    local c = colour(kind)
    if len <= 0 or strands <= 1 then
        seg[#seg + 1] = { c, sr.Vector3(ax, ay, az), sr.Vector3(bx, by, bz) }
        return
    end""",
    """local function add_ribbon(seg, ax, ay, az, bx, by, bz, strands, kind)
    local dx, dy = bx - ax, by - ay
    local len = math.sqrt(dx * dx + dy * dy)
    if len <= 0 or strands <= 1 then
        seg[#seg + 1] = { kind, { ax, ay, az }, { bx, by, bz } }
        return
    end""")

t = t.replace(
    """    for i = -half, half do
        local o = i * step
        seg[#seg + 1] = { c, sr.Vector3(ax + px * o, ay + py * o, az),
                          sr.Vector3(bx + px * o, by + py * o, bz) }
    end""",
    """    for i = -half, half do
        local o = i * step
        seg[#seg + 1] = { kind, { ax + px * o, ay + py * o, az },
                          { bx + px * o, by + py * o, bz } }
    end""")

# 2. The strip's point helper returns plain numbers too.
t = t.replace(
    """        local function at(t, o)
            local x = imp[1] + hx * t + px * o
            local y = imp[2] + hy * t + py * o
            return sr.Vector3(x, y, terrain_height(x, y, imp[3]))
        end""",
    """        local function at(t, o)
            local x = imp[1] + hx * t + px * o
            local y = imp[2] + hy * t + py * o
            return { x, y, terrain_height(x, y, imp[3]) }
        end""")

# 3. The selftest geometry, same treatment.
t = t.replace(
    """            local seg = {}
            add_ribbon(seg, o[1], o[2], o[3] + 1.5, o[1] + 60, o[2], o[3] + 1.5,
                AIR_STRANDS, 'air')""",
    """            local seg = {}
            add_ribbon(seg, o[1], o[2], o[3] + 1.5, o[1] + 60, o[2], o[3] + 1.5,
                AIR_STRANDS, 'air')""")

# 4. Submit builds the engine objects in-frame.
t = t.replace(
    """    local ok = pcall(function()
        sr.LineObject.reset(line)
        for i = 1, #seg do
            local s = seg[i]
            sr.LineObject.add_line(line, s[1], s[2], s[3])
        end
        sr.LineObject.dispatch(world, line)
    end)""",
    """    -- The engine objects are built HERE, in the frame that dispatches them, and never cached:
    -- they live in the script temp arena, which this mod restores at the end of every frame.
    local colors = { air = colour('air'), ground = colour('ground') }
    local ok = pcall(function()
        sr.LineObject.reset(line)
        for i = 1, #seg do
            local s = seg[i]
            sr.LineObject.add_line(line, colors[s[1]],
                sr.Vector3(s[2][1], s[2][2], s[2][3]),
                sr.Vector3(s[3][1], s[3][2], s[3][3]))
        end
        sr.LineObject.dispatch(world, line)
    end)""")

# 5. log_geometry_box reads plain numbers now, so no accessors and no arena risk.
t = t.replace(
    """    local function xyz(v)
        return sr.Vector3.x(v), sr.Vector3.y(v), sr.Vector3.z(v)
    end
    local lo1, lo2, lo3, hi1, hi2, hi3 = nil, nil, nil, nil, nil, nil
    local ok = pcall(function()
        for i = 1, #seg do
            for k = 2, 3 do
                local x, y, z = xyz(seg[i][k])""",
    """    local lo1, lo2, lo3, hi1, hi2, hi3 = nil, nil, nil, nil, nil, nil
    local ok = pcall(function()
        for i = 1, #seg do
            for k = 2, 3 do
                local x, y, z = seg[i][k][1], seg[i][k][2], seg[i][k][3]""")

# 6. colour() must be cheap to call per frame; keep the tiny cache but note why it is safe: it is
#    rebuilt on every submit anyway, so a stale entry cannot survive a frame.
t = t.replace(
    """local function colour(kind)
    if kind == 'ground' then
        if M.color_ground == nil then
            M.color_ground = sr.Color(COLOR_GROUND[1], COLOR_GROUND[2], COLOR_GROUND[3],
                COLOR_GROUND[4])
        end
        return M.color_ground
    end
    if M.color_air == nil then
        M.color_air = sr.Color(COLOR_AIR[1], COLOR_AIR[2], COLOR_AIR[3], COLOR_AIR[4])
    end
    return M.color_air
end""",
    """-- Colours are rebuilt per submission, like the vectors. Caching them was the same mistake:
-- sr.Color allocates in the temp arena too, and this mod restores that arena every frame.
local function colour(kind)
    if kind == 'ground' then
        return sr.Color(COLOR_GROUND[1], COLOR_GROUND[2], COLOR_GROUND[3], COLOR_GROUND[4])
    end
    return sr.Color(COLOR_AIR[1], COLOR_AIR[2], COLOR_AIR[3], COLOR_AIR[4])
end""")

src.write_text(t, encoding="utf-8")
print("changed" if t != before else "NOTHING CHANGED")
for probe in ("sr.Vector3(ax", "sr.Vector3(s[2]", "colors[s[1]]", "local x, y, z = seg[i][k][1]"):
    print("  %-38s %s" % (probe, "present" if probe in t else "MISSING"))
