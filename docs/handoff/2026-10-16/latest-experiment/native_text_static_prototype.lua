-- Offline-only prototype. Nothing is created until P.create is called explicitly.
local P={}

local FONT_PATH='core/performance_hud/debug'
local FONT_MATERIAL='core/performance_hud/debug'
local TEXT='EAGLE FONT'
local FONT_SIZE=1.0
local LAYER=100
local MAX_TTL=10

local function finite(n)
    return type(n)=='number' and n==n and math.abs(n)<math.huge
end

local function world_state(sr,world)
    if world==nil or not sr.Application or type(sr.Application.worlds)~='function' then
        return nil
    end
    local ok,worlds=pcall(sr.Application.worlds)
    if not ok or type(worlds)~='table' then return nil end
    for _,candidate in pairs(worlds) do
        if candidate==world then return true end
    end
    return false
end

local function rollback(sr,world,gui)
    if not gui then return true end
    local state=world_state(sr,world)
    if state==false then return true end
    if state==nil or not sr.World or type(sr.World.destroy_gui)~='function' then return false end
    local ok,result=pcall(sr.World.destroy_gui,world,gui)
    return ok and result~=false
end

local function make_controller(sr,world,gui,expires_at,cleanup_only)
    local controller={}
    local held_sr,held_world,held_gui=sr,world,gui
    local closed=false

    local function release()
        if closed then return true end
        if not held_sr or not held_gui then
            closed=true
            return true
        end
        local state=world_state(held_sr,held_world)
        if state==false then
            held_sr,held_world,held_gui=nil,nil,nil
            closed=true
            return true
        end
        if state==nil or not rollback(held_sr,held_world,held_gui) then
            return false,'GUI destruction unavailable; cleanup may be retried'
        end
        held_sr,held_world,held_gui=nil,nil,nil
        closed=true
        return true
    end

    function controller:cancel()
        return release()
    end

    function controller:tick(time,current_world)
        if closed then return true end
        if cleanup_only then return release() end
        if not finite(time) then return false,'invalid time' end
        if current_world~=nil and current_world~=held_world then return release() end
        local state=world_state(held_sr,held_world)
        if state==false then return release() end
        if state==nil then return false,'world state unknown; cleanup remains pending' end
        if time>=expires_at then return release() end
        return false
    end

    return controller
end

function P.create(sr,world,position,ttl,font_path,now,resource_available)
    if type(sr)~='table' or type(sr.World)~='table' or type(sr.Gui)~='table'
        or type(sr.Application)~='table' or type(sr.Matrix4x4)~='table'
        or type(sr.Matrix4x4.identity)~='function' or sr.Vector3==nil
        or type(sr.World.create_world_gui)~='function'
        or type(sr.World.destroy_gui)~='function'
        or type(sr.Gui.material)~='function' or type(sr.Gui.text_3d)~='function' then
        return nil,'world text API unavailable'
    end
    if type(position)~='table' or not finite(position[1]) or not finite(position[2])
        or not finite(position[3]) or math.abs(position[1])>1e7
        or math.abs(position[2])>1e7 or math.abs(position[3])>1e7 then
        return nil,'invalid position'
    end
    if not finite(ttl) or ttl<=0 or ttl>MAX_TTL or not finite(now)
        or not finite(now+ttl) then return nil,'invalid lifetime' end
    if font_path~=FONT_PATH then return nil,'unsupported font path' end
    if type(resource_available)~='function' then return nil,'resource preflight unavailable' end
    local font_ok,font_found=pcall(resource_available,'font',font_path)
    if not font_ok or font_found~=true then return nil,'font resource unavailable' end
    local material_ok,material_found=pcall(resource_available,'material',FONT_MATERIAL)
    if not material_ok or material_found~=true then return nil,'material resource unavailable' end
    if world_state(sr,world)~=true then return nil,'world unavailable or unknown' end

    local pose_ok,pose=pcall(sr.Matrix4x4.identity)
    if not pose_ok or not pose then return nil,'identity matrix unavailable' end
    local gui_ok,gui=pcall(sr.World.create_world_gui,world,pose,1,1)
    if not gui_ok or not gui then return nil,'world GUI unavailable' end

    local controller=make_controller(sr,world,gui,now+ttl,true)
    local function fail(reason)
        local released=controller:cancel()
        if released then return nil,reason end
        return nil,reason,controller
    end

    local material_bind_ok,bound_material=pcall(sr.Gui.material,gui,FONT_MATERIAL)
    if not material_bind_ok or bound_material==nil or bound_material==false then
        return fail('font material bind failed')
    end

    local vector_ok,point=pcall(sr.Vector3,position[1],position[2],position[3])
    if not vector_ok or not point then
        return fail('position vector unavailable')
    end
    local text_pose_ok,text_pose=pcall(sr.Matrix4x4.identity)
    if not text_pose_ok or not text_pose then
        return fail('text matrix unavailable')
    end
    local text_ok,id=pcall(sr.Gui.text_3d,gui,TEXT,font_path,FONT_SIZE,
        FONT_MATERIAL,text_pose,point,LAYER)
    if not text_ok or not finite(id) or id<0 or id%1~=0 then
        return fail('text creation failed')
    end

    controller=make_controller(sr,world,gui,now+ttl,false)

    return controller
end

return P
