"""Verify that the ground strip follows terrain, rather than only claiming to.

Runs the harness's own drive (which reliably produces an impact point and a strip) and then
re-measures the SAME strip against three kinds of terrain sample:

  no samples     -> flat at the impact height (option A behaviour, the graceful fallback)
  flat samples   -> still flat
  sloped samples -> the strip's vertices span a real height range

If the third case does not differ from the first two, the interpolation is decorative.
"""
import os
import pathlib
import tempfile

from lupa import LuaRuntime

ROOT = pathlib.Path(__file__).resolve().parents[2]      # mods/eagle-direction-probe
PROBE = ROOT / "src" / "eagle_direction_probe.lua"
HARNESS = pathlib.Path(__file__).resolve().parent / "harness_draw.lua"

SCENARIO = r"""
-- The harness has already driven a throw and a pass, so an impact point and a strip exist.
local function ground_stats()
    local lo, hi, n = nil, nil, 0
    if M.seg ~= nil then
        for i = 1, #M.seg do
            local s = M.seg[i]
            -- The ground colour is white at alpha 235; the air ribbon is white at alpha 170.
            if s[1] ~= nil and s[1].a == 235 then
                n = n + 1
                for k = 2, 3 do
                    local z = s[k][3]
                    if lo == nil or z < lo then lo = z end
                    if hi == nil or z > hi then hi = z end
                end
            end
        end
    end
    return lo, hi, n
end

local function report(label)
    local impacts = 0
    for _ in pairs(M.impacts) do impacts = impacts + 1 end
    local total = (M.seg ~= nil) and #M.seg or -1
    local lo, hi, n = ground_stats()
    if n == 0 then
        print(string.format('%-16s NO GROUND STRIP  [seg=%d impacts=%d ground=%d]',
            label, total, impacts, #M.ground))
        return
    end
    print(string.format('%-16s strip_segments=%-3d ground_at_build=%-3d z_min=%7.2f '
        .. 'z_max=%7.2f spread=%6.2f m', label, n, #M.ground, lo, hi, hi - lo))
    if M.ground[1] then
        print(string.format('%-16s   first sample: x=%.1f y=%.1f z=%.1f',
            '', M.ground[1][1], M.ground[1][2], M.ground[1][3]))
    end
end

local function rebuild_with(samples)
    M.ground = samples
    -- Perturb the impact point so the geometry key changes and the next frame rebuilds.
    -- 0.5 m, not 0.01: the key formats positions to one decimal, so a smaller nudge rounds to
    -- the same string and the geometry is never rebuilt - which made the first version of this
    -- check report every case as flat.
    for _, imp in pairs(M.impacts) do
        imp.p[1] = imp.p[1] + 0.5
    end
    tick(3)
end

report('no samples')
rebuild_with({})
report('still none')

-- Flat ground: every sample at the same height.
rebuild_with({ { 0, 0, 32, 0 }, { 120, 40, 32, 0 }, { -80, 60, 32, 0 } })
report('flat samples')

-- A hillside: the samples climb 40 m across the area.
rebuild_with({ { 0, 0, 12, 0 }, { 120, 40, 34, 0 }, { -80, 60, 52, 0 } })
report('sloped samples')

-- And back to a single flat sample, to show the strip is not stuck on the slope.
rebuild_with({ { 0, 0, 32, 0 } })
report('flat again')
"""


def main():
    os.environ["DSH_HARNESS_TMP"] = tempfile.mkdtemp(prefix="terrain-")
    os.environ["DSH_PROBE_PATH"] = str(PROBE)
    os.environ["DSH_HARNESS_MODE"] = "normal"
    src = HARNESS.read_text(encoding="utf-8")
    src += SCENARIO          # same chunk, so the harness's locals (M, tick) are in scope
    print("=" * 78)
    print("Does the ground strip follow terrain?")
    print("=" * 78)
    LuaRuntime(unpack_returned_tuples=True).execute(src)


if __name__ == "__main__":
    main()
