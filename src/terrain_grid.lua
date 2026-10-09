-- HD2-Addon: mods/codex/eagle_terrain_grid
-- Pure terrain sample-grid planning and bilinear interpolation. No engine/native access.
local G = {}

local function finite(value)
    return type(value) == 'number' and value == value
        and value > -math.huge and value < math.huge
end

local function even_at_least(value, minimum)
    local n = math.max(minimum, math.ceil(value))
    if n % 2 ~= 0 then n = n + 1 end
    return n
end

function G.plan(bounds, border_halfwidth)
    if type(bounds) ~= 'table' then return nil end
    if border_halfwidth == nil then border_halfwidth = 0.25 end
    if not finite(border_halfwidth) or border_halfwidth < 0 then return nil end

    local shape = bounds.shape
    if shape ~= 'strip' and shape ~= 'circle' and shape ~= 'direction' then return nil end

    local lo, hi, width, n, rows
    if shape == 'circle' then
        local radius = bounds.radius
        if not finite(radius) or radius <= 0 then return nil end
        -- The border is radius +/- border_halfwidth. The extra quarter metre keeps
        -- panel/rounding consumers inside the sampled grid as well.
        local extent = radius + border_halfwidth + 0.25
        lo, hi, width = -extent, extent, extent
        n, rows = 8, 7
    else
        if not finite(bounds.lo) or not finite(bounds.hi) or bounds.hi <= bounds.lo
            or not finite(bounds.half) or bounds.half < 0 then return nil end
        lo, hi = bounds.lo - border_halfwidth, bounds.hi + border_halfwidth
        width = bounds.half + border_halfwidth + 0.25
        if width <= 0 then return nil end
        local length = hi - lo
        if shape == 'direction' or length > 100 then
            -- Preserve the long guide's axial density without trading it for rows.
            n, rows = even_at_least(length / 8.5, 24), 3
        else
            n, rows = 10, 5
        end
    end

    local total = (n + 1) * rows
    -- The supported catalog grids remain within the existing per-guide query budget.
    if total > 85 then return nil end

    local offsets = {}
    for row = 1, rows do
        offsets[row] = -width + 2 * width * (row - 1) / (rows - 1)
    end
    local signature = table.concat({shape, tostring(lo), tostring(hi), tostring(width),
        tostring(n), tostring(rows)}, ':')
    return {
        lo = lo, hi = hi, width = width, n = n, rows = rows,
        row_offsets = offsets, total = total, signature = signature,
    }
end

-- Merge the display-clipped endpoints with every cached axial sample inside them.
-- This refines mesh tessellation at known terrain stations without issuing queries.
function G.stations(grid, lo, hi)
    if type(grid) ~= 'table' or not finite(grid.lo) or not finite(grid.hi)
        or grid.hi <= grid.lo or not finite(grid.n) or grid.n < 1
        or grid.n > 1000000 or grid.n % 1 ~= 0
        or not finite(lo) or not finite(hi) or hi < lo then return nil end
    local eps = 1e-9
    if lo < grid.lo - eps or hi > grid.hi + eps then return nil end
    lo, hi = math.max(lo, grid.lo), math.min(hi, grid.hi)

    local result = {lo}
    local step = (grid.hi - grid.lo) / grid.n
    for k = 0, grid.n do
        local station = grid.lo + step * k
        if station > lo + eps and station < hi - eps then
            result[#result + 1] = station
        end
    end
    if hi - result[#result] > eps then result[#result + 1] = hi end
    return result
end

-- `grid.h` follows the collision-grid cache layout: zero-based axial station k,
-- one-based row r, flattened as k * grid.rows + r. A false/nil corner is a MISS.
local function grid_metadata(grid)
    if type(grid) ~= 'table' or type(grid.h) ~= 'table'
        or not finite(grid.lo) or not finite(grid.hi) or grid.hi <= grid.lo
        or not finite(grid.width) or grid.width <= 0
        or not finite(grid.n) or grid.n < 1 or grid.n % 1 ~= 0
        or not finite(grid.rows) or grid.rows < 2 or grid.rows % 1 ~= 0 then return nil end
    return grid.h, grid.lo, grid.hi, grid.width, grid.n, grid.rows
end

local function sample(h, lo, hi, width, n, rows, along, lateral)
    if not finite(along) or not finite(lateral) then return nil end
    local eps = 1e-9
    if along < lo - eps or along > hi + eps
        or lateral < -width - eps or lateral > width + eps then return nil end
    along = math.max(lo, math.min(hi, along))
    lateral = math.max(-width, math.min(width, lateral))

    local u = (along - lo) * n / (hi - lo)
    local v = (lateral + width) * (rows - 1) / (2 * width)
    local i, j = math.floor(u), math.floor(v)
    if i >= n then i = n - 1 end
    if j >= rows - 1 then j = rows - 2 end
    local a, b = u - i, v - j
    local wa, wb, wc, wd = (1 - a) * (1 - b), a * (1 - b), (1 - a) * b, a * b
    local ha, hb = h[i * rows + j + 1], h[(i + 1) * rows + j + 1]
    local hc, hd = h[i * rows + j + 2], h[(i + 1) * rows + j + 2]
    if (wa > eps and not finite(ha)) or (wb > eps and not finite(hb))
        or (wc > eps and not finite(hc)) or (wd > eps and not finite(hd)) then return nil end
    return (wa > eps and ha * wa or 0) + (wb > eps and hb * wb or 0)
        + (wc > eps and hc * wc or 0) + (wd > eps and hd * wd or 0)
end

-- Validate fixed grid metadata once; the captured height table remains live so
-- terrain_tick can fill MISS slots without rebuilding this sampler.
function G.bind(grid)
    local h, lo, hi, width, n, rows = grid_metadata(grid)
    if not h then return nil end
    return function(along, lateral)
        return sample(h, lo, hi, width, n, rows, along, lateral)
    end
end

function G.height(grid, along, lateral)
    local h, lo, hi, width, n, rows = grid_metadata(grid)
    if not h then return nil end
    return sample(h, lo, hi, width, n, rows, along, lateral)
end

return G
