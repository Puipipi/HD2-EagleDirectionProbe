-- HD2-Addon: mods/codex/eagle_cordon_view
-- Pure view-side selection for one lettering panel.
-- Vectors are dense {x, y, z} arrays. This module does not own or mutate them.
local EPSILON_METERS = 0.05

local function finite_number(value)
    return type(value) == "number"
        and value == value
        and value ~= math.huge
        and value ~= -math.huge
end

local function valid_vector(vector)
    if type(vector) ~= "table" then
        return false
    end
    return finite_number(vector[1])
        and finite_number(vector[2])
        and finite_number(vector[3])
end

local function valid_side(side)
    return side == "outer" or side == "inner"
end

local function choose(viewer_p, center_p, outward_normal, last_side)
    if viewer_p == nil then
        if valid_side(last_side) then
            return last_side
        end
        return nil
    end

    if not valid_vector(viewer_p)
        or not valid_vector(center_p)
        or not valid_vector(outward_normal) then
        return nil
    end

    local nx, ny, nz = outward_normal[1], outward_normal[2], outward_normal[3]
    local normal_sq = nx * nx + ny * ny + nz * nz
    if not finite_number(normal_sq) or normal_sq <= 0 then
        return nil
    end

    local dx = viewer_p[1] - center_p[1]
    local dy = viewer_p[2] - center_p[2]
    local dz = viewer_p[3] - center_p[3]
    local signed_distance = (dx * nx + dy * ny + dz * nz) / math.sqrt(normal_sq)
    if not finite_number(signed_distance) then
        return nil
    end

    if math.abs(signed_distance) <= EPSILON_METERS and valid_side(last_side) then
        return last_side
    end
    if signed_distance < 0 then
        return "inner"
    end
    -- The exact plane is a deterministic outer tie, so a panel is never
    -- emitted on both sides when the viewer lies on its plane.
    return "outer"
end

return { choose = choose }
