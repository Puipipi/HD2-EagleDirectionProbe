-- HD2-Addon: mods/codex/eagle_native_light_probe
-- Optional native-light experiment, using a separately installed headlamp resource.
-- Own local helper instances only. No imported assets, memory access or Runtime.
local P={}
local RESOURCE='content/helmet_headlamp/runtime_mode_profiles'
local LIGHT='helmet_headlamp_task_fill'
local function point(p)
    if type(p)~='table' then return false end
    for i=1,3 do
        if type(p[i])~='number' or p[i]~=p[i] or math.abs(p[i])>100000 then return false end
    end
    return true
end

function P.new(sr)
    local required={Application={'worlds','can_get'},World={'spawn_unit','destroy_unit','update_unit'},
        Unit={'alive','node','num_lights','has_light','light','set_local_position',
            'set_local_rotation','set_unit_visibility'},Quaternion={'axis_angle'},
        Light={'set_enabled','set_color','set_spot_angle_start','set_spot_angle_end','set_falloff_end'}}
    for namespace,names in pairs(required) do for _,name in ipairs(names) do
        if type(sr[namespace])~='table' or type(sr[namespace][name])~='function' then
            return nil,namespace..'.'..name..' unavailable'
        end
    end end
    -- HD2 exposes Vector3 as a callable table, not a Lua function.
    if not pcall(function() return sr.Vector3(0,0,0) end) then return nil,'Vector3 unavailable' end
    local self={rows={},count=0,status='idle',retry_at=0}
    local function live(world)
        if world==nil then return false end
        local ok,worlds=pcall(sr.Application.worlds)
        if ok and type(worlds)=='table' then
            for _,w in pairs(worlds) do if w==world then return true end end
        end
        return false
    end
    local function alive(unit)
        local ok,result=pcall(sr.Unit.alive,unit)
        return ok and result==true
    end
    local function destroy(row,world_is_live)
        if not world_is_live or not alive(row.unit) then return end
        for i=0,(row.lights or 0)-1 do
            local ok,l=pcall(sr.Unit.light,row.unit,i)
            if ok and l then pcall(sr.Light.set_enabled,l,false) end
        end
        pcall(sr.World.destroy_unit,self.world,row.unit)
    end
    function self:release()
        local current=live(self.world)
        for _,row in pairs(self.rows) do destroy(row,current) end
        self.rows,self.world,self.count={},nil,0
        self.ready,self.retry_at=nil,0
    end
    local function position(row,p)
        sr.Unit.set_local_position(row.unit,row.node,sr.Vector3(p[1],p[2],p[3]+12))
        sr.World.update_unit(self.world,row.unit)
        row.x,row.y,row.z=p[1],p[2],p[3]
    end
    local function create(p)
        local ok,unit=pcall(sr.World.spawn_unit,self.world,RESOURCE)
        if not ok or not unit then return nil,'helper spawn unavailable' end
        local row={unit=unit}
        local configured,reason=pcall(function()
            assert(alive(unit),'spawned helper unavailable')
            row.node=sr.Unit.node(unit,'StingrayEntityRoot')
            assert(type(row.node)=='number' and row.node>=0,'root node unavailable')
            row.lights=sr.Unit.num_lights(unit)
            assert(row.lights==5,'headlamp resource profile unavailable')
            for i=0,4 do sr.Light.set_enabled(sr.Unit.light(unit,i),false) end
            assert(sr.Unit.has_light(unit,LIGHT),'task light unavailable')
            local light=sr.Unit.light(unit,LIGHT)
            -- This HD2 asset stores HDR radiance (its white task fill is 9000,
            -- 8550,7560 at intensity 1), rather than a normalized GUI colour.
            sr.Light.set_color(light,sr.Vector3(7000,120,180))
            sr.Light.set_spot_angle_start(light,2*math.atan(8/12))
            sr.Light.set_spot_angle_end(light,2*math.atan(16/12))
            sr.Light.set_falloff_end(light,25)
            if type(sr.Light.set_casts_shadows)=='function' then sr.Light.set_casts_shadows(light,false) end
            if type(sr.Light.set_volumetric_enabled)=='function' then sr.Light.set_volumetric_enabled(light,false) end
            sr.Unit.set_unit_visibility(unit,false)
            -- Stingray units look along +Y; rotate the owned emitter toward -Z.
            sr.Unit.set_local_rotation(unit,row.node,
                sr.Quaternion.axis_angle(sr.Vector3(1,0,0),-math.pi/2))
            position(row,p)
            sr.Light.set_enabled(light,true)
        end)
        if not configured then destroy(row,live(self.world));return nil,tostring(reason) end
        return row
    end
    function self:sync(world,impacts,now)
        if world~=self.world then self:release();self.world=world end
        if not live(world) then self:release();self.status='world unavailable';return false,self.status,0 end
        -- Retire immediately even during spawn retry backoff. Only own helpers
        -- are touched; existing headlamp units and their settings are never read.
        for id,row in pairs(self.rows) do
            local imp=impacts[id]
            if not imp or not point(imp.p) or not alive(row.unit) then
                destroy(row,true);self.rows[id]=nil
            elseif row.x~=imp.p[1] or row.y~=imp.p[2] or row.z~=imp.p[3] then
                local ok=pcall(position,row,imp.p)
                if not ok then destroy(row,true);self.rows[id]=nil;self.retry_at=now+1 end
            end
        end
        if not self.ready and now>=self.retry_at and next(impacts) then
            local ok,available=pcall(sr.Application.can_get,'unit',RESOURCE)
            self.ready=ok and available==true
            if not self.ready then self.retry_at=now+1;self.status='headlamp resource unavailable' end
        end
        if self.ready and now>=self.retry_at then
            -- Bound creation bursts, not active guide counts. Every guide can
            -- eventually own one light; stationary lights receive no updates.
            for id,imp in pairs(impacts) do if not self.rows[id] and point(imp.p) then
                local row,why=create(imp.p)
                if row then self.rows[id]=row;self.status='native red spotlight active (prototype)'
                else self.status='native light unavailable: '..why;self.retry_at=now+1 end
                break
            end end
        end
        local n=0;for _ in pairs(self.rows) do n=n+1 end;self.count=n
        if not next(impacts) then self.status='idle' end
        return n>0,self.status,n
    end
    return self
end
return P
