"""Is the arrowhead GEOMETRICALLY a closed triangle, or only textually one?

Last round I closed the head by adding a base line, and the test for it greps the source for that
line. That proves the code is present, not that the shape closes. This builds the graph of segment
endpoints from the generated geometry and looks for an actual triangle.

The player described the old head as "at least three straight lines intersecting at one point" -
a star. A closed triangle has three vertices of degree 2 whose three edges form a cycle, which is
a different graph, and this test tells them apart.
"""
import os
import pathlib
import tempfile

from lupa import LuaRuntime

ROOT = pathlib.Path(__file__).resolve().parents[2]      # mods/eagle-direction-probe
PROBE = ROOT / "src" / "eagle_direction_probe.lua"
HARNESS = pathlib.Path(__file__).resolve().parent / "harness_draw.lua"

SCENARIO = r"""
local function key(v) return string.format('%.2f,%.2f,%.2f', v[1], v[2], v[3]) end

local verts, edges = {}, {}
local function vertex(v)
    local k = key(v)
    verts[k] = verts[k] or { key = k, v = { v[1], v[2], v[3] }, deg = 0 }
    verts[k].deg = verts[k].deg + 1
    return k
end
for i = 1, #M.seg do
    local s = M.seg[i]
    local a, b = vertex(s[2]), vertex(s[3])
    if a ~= b then edges[a .. '|' .. b] = true; edges[b .. '|' .. a] = true end
end

-- Find a triangle: three vertices each joined to the other two.
local keys = {}
for k in pairs(verts) do keys[#keys + 1] = k end
local found = 0
for i = 1, #keys do
    for j = i + 1, #keys do
        if edges[keys[i] .. '|' .. keys[j]] then
            for l = j + 1, #keys do
                if edges[keys[i] .. '|' .. keys[l]] and edges[keys[j] .. '|' .. keys[l]] then
                    found = found + 1
                    if found == 1 then
                        local function len(a, b)
                            local dx = a[1]-b[1]; local dy = a[2]-b[2]; local dz = a[3]-b[3]
                            return math.sqrt(dx*dx + dy*dy + dz*dz)
                        end
                        local va, vb, vc = verts[keys[i]].v, verts[keys[j]].v, verts[keys[l]].v
                        print(string.format('TRIANGLE verts=%d edges=%.1f/%.1f/%.1f m',
                            #keys, len(va,vb), len(va,vc), len(vb,vc)))
                    end
                end
            end
        end
    end
end
print(string.format('RESULT distinct_endpoints=%d edges=%d triangles=%d',
    #keys, (function() local n = 0 for _ in pairs(edges) do n = n + 1 end return n // 2 end)(), found))
"""


def main():
    tmp = tempfile.mkdtemp(prefix="shapes-")
    os.makedirs(os.path.join(tmp, "CowboyBingus", "Helldivers2", "Logs"), exist_ok=True)
    os.environ["DSH_HARNESS_TMP"] = tmp
    os.environ["DSH_PROBE_PATH"] = str(PROBE)
    os.environ["DSH_HARNESS_MODE"] = "normal"
    src = HARNESS.read_text(encoding="utf-8")
    # Run the check while the aircraft IS STILL FLYING. Appending after the whole drive put it
    # after the aircraft had left, so only the ground strip existed and the check found no
    # triangle - a test of the wrong moment, not a finding about the shape.
    marker = "-- The aircraft leaves"
    head, tail = src.split(marker, 1)
    src = head + SCENARIO + "\n" + marker + tail
    print("=" * 70)
    print("Does the arrowhead close into a triangle?")
    print("=" * 70)
    LuaRuntime(unpack_returned_tuples=True).execute(src)


if __name__ == "__main__":
    main()
