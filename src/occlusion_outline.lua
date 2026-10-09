-- HD2-Addon: mods/codex/eagle_occlusion_outline
-- Pure Lua boundary extraction/dashing for a depth-tested outline pass.
-- Input/output contain ordinary point tables only; no engine or native objects.
local O = {}
local WELD = 0.00001

local function finite(n)
    return type(n) == 'number' and n == n and n > -math.huge and n < math.huge
        and math.abs(n) <= 1e7
end

local function read_point(p)
    if type(p) ~= 'table' then return nil end
    local x, y, z = p[1], p[2], p[3]
    if not finite(x) or not finite(y) or not finite(z) then return nil end
    return {x, y, z}
end

local function valid_point(p)
    return type(p) == 'table' and finite(p[1]) and finite(p[2]) and finite(p[3])
end

local function length2(a, b)
    local x, y, z = b[1] - a[1], b[2] - a[2], b[3] - a[3]
    return x*x + y*y + z*z
end

local function area2(a, b, c)
    local ax, ay, az = b[1] - a[1], b[2] - a[2], b[3] - a[3]
    local bx, by, bz = c[1] - a[1], c[2] - a[2], c[3] - a[3]
    local x, y, z = ay*bz - az*by, az*bx - ax*bz, ax*by - ay*bx
    return x*x + y*y + z*z
end

function O.build(batch)
    if type(batch) ~= 'table' then return {} end
    local buckets, vertices, point_ids = {}, {}, {}
    local groups, edge_order, authored = {}, {}, {}

    local function vertex_id(p)
        local cached = point_ids[p]
        if cached then return cached end
        local x, y, z = p[1], p[2], p[3]
        -- Grid-snap welding: points with the same rounded 1e-5 m integer triplet
        -- share an ID. Points on opposite snap-bin sides intentionally remain apart.
        local qx, qy, qz = math.floor(x / WELD + 0.5),
            math.floor(y / WELD + 0.5), math.floor(z / WELD + 0.5)
        local by_x = buckets[qx]
        if not by_x then by_x = {}; buckets[qx] = by_x end
        local by_y = by_x[qy]
        if not by_y then by_y = {}; by_x[qy] = by_y end
        local id = by_y[qz]
        if not id then
            id = #vertices + 1
            vertices[id] = {x, y, z}
            by_y[qz] = id
        end
        point_ids[p] = id
        return id
    end

    local function count_edge(kind, a, b)
        if a == b or length2(vertices[a], vertices[b]) <= 1e-18 then return end
        local low, high = a, b
        if low > high then low, high = high, low end
        local group = groups[kind]
        if not group then group = {}; groups[kind] = group end
        local by_low = group[low]
        if not by_low then by_low = {}; group[low] = by_low end
        local edge = by_low[high]
        if not edge then
            edge = {kind = kind, a = a, b = b, count = 0}
            by_low[high] = edge
            edge_order[#edge_order + 1] = edge
        end
        edge.count = edge.count + 1
    end

    for _, record in ipairs(batch) do
        if type(record) == 'table' and type(record[1]) == 'string' then
            local kind = record[1]
            if record[4] ~= nil then
                local p1, p2, p3 = record[2], record[3], record[4]
                if valid_point(p1) and valid_point(p2) and valid_point(p3)
                    and area2(p1, p2, p3) > 1e-18 then
                    local id1, id2, id3 = vertex_id(p1), vertex_id(p2), vertex_id(p3)
                    count_edge(kind, id1, id2)
                    count_edge(kind, id2, id3)
                    count_edge(kind, id3, id1)
                end
            else
                local p1, p2 = read_point(record[2]), read_point(record[3])
                if p1 and p2 and length2(p1, p2) > 1e-18 then
                -- Explicit strokes (including text) are preserved as separate records.
                authored[#authored + 1] = {kind = kind, p1 = p1, p2 = p2,
                    source_line = true}
                end
            end
        end
    end

    local result = {}
    for _, edge in ipairs(edge_order) do
        if edge.kind == 'marker' or edge.count == 1 then
            result[#result + 1] = {kind = edge.kind, p1 = read_point(vertices[edge.a]),
                p2 = read_point(vertices[edge.b]),
                source_line = false}
        end
    end
    for _, line in ipairs(authored) do result[#result + 1] = line end
    return result
end

function O.dash(lines, dash_m, gap_m)
    if dash_m == nil then dash_m = 1.2 end
    if gap_m == nil then gap_m = 0.8 end
    if not finite(dash_m) or not finite(gap_m) or dash_m <= 0 or gap_m < 0 then return {} end
    if type(lines) ~= 'table' then return {} end
    local result = {}
    for _, line in ipairs(lines) do
        if type(line) == 'table' and type(line.kind) == 'string' then
            local a, b = read_point(line.p1), read_point(line.p2)
            if a and b then
                local length = math.sqrt(length2(a, b))
                if length > 1e-9 then
                    if length <= dash_m then
                        result[#result + 1] = {kind = line.kind, p1 = a, p2 = b,
                            source_line = line.source_line}
                    else
                        local distance = 0
                        while distance < length do
                            local finish = math.min(length, distance + dash_m)
                            local t0, t1 = distance / length, finish / length
                            result[#result + 1] = {
                                kind = line.kind,
                                source_line = line.source_line,
                                p1 = {a[1] + (b[1]-a[1])*t0,
                                    a[2] + (b[2]-a[2])*t0,
                                    a[3] + (b[3]-a[3])*t0},
                                p2 = {a[1] + (b[1]-a[1])*t1,
                                    a[2] + (b[2]-a[2])*t1,
                                    a[3] + (b[3]-a[3])*t1},
                            }
                            distance = finish + gap_m
                        end
                    end
                end
            end
        end
    end
    return result
end

return O
