-- HD2-Addon: mods/codex/eagle_native_light_probe
-- Optional native-light experiment, using a separately installed headlamp resource.
-- Own local helper instances only. No imported assets, memory access or Runtime.
local P={}
local RESOURCE='content/helmet_headlamp/runtime_mode_profiles'
local LIGHT='helmet_headlamp_task_fill'
local FUNCTIONAL_LIGHTS={
    'helmet_headlamp_task_fill','helmet_headlamp_task_soft_reach',
    'helmet_headlamp_gameplay_fill','helmet_headlamp_gameplay_direction',
}
local MARKER_LIGHTS={'helmet_headlamp_default_task','helmet_headlamp_default_gameplay'}
local function point(p)
    if type(p)~='table' then return false end
    for i=1,3 do
        if type(p[i])~='number' or p[i]~=p[i] or math.abs(p[i])>100000 then return false end
    end
    return true
end

function P.new(sr)
    local required={Application={'worlds','can_get'},World={'spawn_unit','update_unit','destroy_unit'},
        Unit={'alive','node','light','set_local_position',
            'set_local_rotation','set_unit_visibility'},Quaternion={'axis_angle'},
        Light={'set_enabled','set_color','set_intensity'}}
    local missing={}
    for namespace,names in pairs(required) do for _,name in ipairs(names) do
        if type(sr[namespace])~='table' or type(sr[namespace][name])~='function' then
            missing[#missing+1]=namespace..'.'..name
        end
    end end
    -- HD2 exposes Vector3 as a callable table, not a Lua function.
    if not pcall(function() return sr.Vector3(0,0,0) end) then
        missing[#missing+1]='Vector3 callable'
    end
    if #missing>0 then
        table.sort(missing)
        return nil,'required APIs unavailable: '..table.concat(missing,', ')
    end
    local self={rows={},count=0,status='idle',retry_at=0,
        diagnostic_world=nil,diagnostic_mode=nil,diagnostic_reported=false,
        color_diagnostic=nil,pending_color_diagnostic=nil}
    local function color_text(light)
        if type(sr.Light.color)~='function' then return 'unavailable' end
        local ok,value=pcall(sr.Light.color,light)
        if not ok then return 'error' end
        if value==nil then return 'nil' end
        local read,x,y,z=pcall(function()
            return sr.Vector3.x(value),sr.Vector3.y(value),sr.Vector3.z(value)
        end)
        if not read or type(x)~='number' or type(y)~='number' or type(z)~='number' then
            return 'unreadable'
        end
        return string.format('%.6g,%.6g,%.6g',x,y,z)
    end
    local function intensity_text(light)
        if type(sr.Light.intensity)~='function' then return 'unavailable' end
        local ok,value=pcall(sr.Light.intensity,light)
        if not ok then return 'error' end
        if type(value)~='number' then return value==nil and 'nil' or 'unreadable' end
        return string.format('%.6g',value)
    end
    local function vector_text(value)
        if value==nil or type(sr.Vector3)~='table' or type(sr.Vector3.x)~='function'
            or type(sr.Vector3.y)~='function' or type(sr.Vector3.z)~='function' then
            return 'unavailable'
        end
        local ok,x,y,z=pcall(function()
            return sr.Vector3.x(value),sr.Vector3.y(value),sr.Vector3.z(value)
        end)
        if not ok or type(x)~='number' or type(y)~='number' or type(z)~='number'
            or x~=x or y~=y or z~=z then return 'unreadable' end
        return string.format('%.6g,%.6g,%.6g',x,y,z)
    end
    local function transform_text(row,p)
        local expected=string.format('%.6g,%.6g,%.6g',p[1],p[2],p[3]+12)
        local actual,forward='unavailable','unavailable'
        if type(sr.Unit.world_position)=='function' then
            local ok,value=pcall(sr.Unit.world_position,row.unit,row.node)
            actual=ok and vector_text(value) or 'error'
        end
        if type(sr.Unit.world_pose)=='function' and type(sr.Matrix4x4)=='table'
            and type(sr.Matrix4x4.forward)=='function' then
            local ok_pose,pose=pcall(sr.Unit.world_pose,row.unit,row.node)
            if ok_pose and pose~=nil then
                local ok_forward,value=pcall(sr.Matrix4x4.forward,pose)
                forward=ok_forward and vector_text(value) or 'error'
            else
                forward=ok_pose and 'nil' or 'error'
            end
        end
        return 'expected_pos='..expected..' world_pos='..actual..' root_forward='..forward
    end
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
        for _,light in ipairs(row.lights or {}) do
            if light then pcall(sr.Light.set_enabled,light,false) end
        end
        pcall(sr.World.destroy_unit,self.world,row.unit)
    end
    function self:release()
        if next(self.rows)==nil then
            self.rows,self.world,self.count={},nil,0
            self.ready,self.retry_at=nil,0
            return
        end
        local current=live(self.world)
        for _,row in pairs(self.rows) do destroy(row,current) end
        self.rows,self.world,self.count={},nil,0
        self.ready,self.retry_at=nil,0
    end
    local function position(row,p,capture_diagnostic)
        sr.Unit.set_local_position(row.unit,row.node,sr.Vector3(p[1],p[2],p[3]+12))
        -- Explicitly refresh the local transform as the installed controller does.
        sr.World.update_unit(self.world,row.unit)
        local transform=capture_diagnostic and transform_text(row,p) or nil
        row.x,row.y,row.z=p[1],p[2],p[3]
        return transform
    end
    local function create(p,authored_color,frame_token)
        local ok,unit=pcall(sr.World.spawn_unit,self.world,RESOURCE)
        if not ok or not unit then return nil,'helper spawn unavailable' end
        local row={unit=unit,lights={}}
        local configured,reason=pcall(function()
            assert(alive(unit),'spawned helper unavailable')
            row.node=sr.Unit.node(unit,'StingrayEntityRoot')
            assert(type(row.node)=='number' and row.node>=0,'root node unavailable')
            local resolved={}
            for _,name in ipairs(FUNCTIONAL_LIGHTS) do
                local ok,light=pcall(sr.Unit.light,unit,name)
                assert(ok and light,name..' unavailable in headlamp resource profile')
                resolved[name]=light
                row.lights[#row.lights+1]=light
            end
            local light=resolved[LIGHT]
            local capture_diagnostic=not self.diagnostic_reported
            local before_color=capture_diagnostic and color_text(light) or nil
            local before_intensity=capture_diagnostic and intensity_text(light) or nil
            for _,name in ipairs(MARKER_LIGHTS) do
                local should_resolve=true
                if type(sr.Unit.has_light)=='function' then
                    local checked,present=pcall(sr.Unit.has_light,unit,name)
                    if checked then should_resolve=present==true end
                end
                if should_resolve then
                    local ok,marker=pcall(sr.Unit.light,unit,name)
                    if ok and marker then row.lights[#row.lights+1]=marker end
                end
            end
            for _,owned_light in ipairs(row.lights) do
                sr.Light.set_enabled(owned_light,false)
            end
            if type(sr.Unit.num_lights)=='function' then
                local ok,count=pcall(sr.Unit.num_lights,unit)
                assert(ok and count==5,'headlamp resource profile unavailable')
            end
            -- Purple is the normal comparison. Authored mode skips both setters so
            -- the resource's original light values can be compared without edits.
            if authored_color then
                if capture_diagnostic then
                    row.color_diagnostic=string.format('mode=authored setters_skipped=true '
                        ..'before_color=%s before_intensity=%s after_color=%s after_intensity=%s',
                        before_color,before_intensity,color_text(light),intensity_text(light))
                end
            else
                sr.Light.set_color(light,sr.Vector3(1,0,1))
                sr.Light.set_intensity(light,7000)
                if capture_diagnostic then
                    row.color_diagnostic=string.format('mode=purple setters_skipped=false '
                        ..'before_color=%s before_intensity=%s set_color=1,0,1 '
                        ..'set_intensity=7000 after_color=%s after_intensity=%s',
                        before_color,before_intensity,color_text(light),intensity_text(light))
                end
            end
            -- Preserve this installed resource's authored cone, falloff and render flags.
            -- These Light setters are not part of the APIs verified in the installed
            -- headlamp controller, and partial cone writes could invert inner/outer.
            sr.Unit.set_unit_visibility(unit,false)
            -- Preserve the existing exporter-axis assumption (+Y rotated toward -Z);
            -- root_forward readback does not prove the embedded beam's local axis.
            sr.Unit.set_local_rotation(unit,row.node,
                sr.Quaternion.axis_angle(sr.Vector3(1,0,0),-math.pi/2))
            local transform_diagnostic=position(row,p,capture_diagnostic)
            sr.Light.set_enabled(light,true)
            row.target_light=light
            row.enabled_frame=frame_token
            if capture_diagnostic then
                row.color_diagnostic=row.color_diagnostic..' '..transform_diagnostic
            end
        end)
        if not configured then destroy(row,live(self.world));return nil,tostring(reason) end
        if not self.diagnostic_reported then
            self.color_diagnostic=row.color_diagnostic
            self.pending_color_diagnostic=row.color_diagnostic
            self.diagnostic_reported=true
            self.diagnostic_world=self.world
            self.diagnostic_mode=self.mode
        end
        return row
    end
    function self:sync(world,impacts,now,authored_color,frame_token)
        authored_color=authored_color==true
        local mode=authored_color and 'authored' or 'purple'
        if self.mode~=nil and self.mode~=mode then self:release() end
        self.mode=mode
        if world~=self.world then
            self:release();self.world=world
        end
        if world~=self.diagnostic_world or mode~=self.diagnostic_mode then
            self.diagnostic_reported=false
        end
        if not next(impacts) and not next(self.rows) then
            self.status='idle';self.count=0
            return false,self.status,0
        end
        if not live(world) then self:release();self.status='world unavailable';return false,self.status,0 end
        -- Retire immediately even during spawn retry backoff. Only own helpers
        -- are touched; existing headlamp units and their settings are never read.
        for id,row in pairs(self.rows) do
            local imp=impacts[id]
            if not imp or not point(imp.p) or not alive(row.unit) then
                destroy(row,true);self.rows[id]=nil
            elseif row.x~=imp.p[1] or row.y~=imp.p[2] or row.z~=imp.p[3] then
                local ok=pcall(position,row,imp.p,false)
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
            -- eventually own one light; stationary lights receive no transform updates.
            for id,imp in pairs(impacts) do if not self.rows[id] and point(imp.p) then
                local row,why=create(imp.p,authored_color,frame_token)
                if row then
                    self.rows[id]=row
                    self.status=authored_color and 'native authored-color spotlight test active (prototype)'
                        or 'native violet spotlight test active (prototype)'
                else self.status='native light unavailable: '..why;self.retry_at=now+1 end
                break
            end end
        end
        local n=0;for _ in pairs(self.rows) do n=n+1 end;self.count=n
        if not next(impacts) then self.status='idle' end
        local diagnostic=self.pending_color_diagnostic
        self.pending_color_diagnostic=nil
        return n>0,self.status,n,diagnostic
    end
    function self:keep_alive(impacts,catalog,frame_token,now,type_epoch)
        for id,row in pairs(self.rows) do
            local imp=impacts[id]
            if not imp or not catalog or not catalog[imp.stratagem_type]
                or type_epoch==nil or imp.type_epoch~=type_epoch
                or not point(imp.p) or not alive(row.unit) then
                destroy(row,live(self.world));self.rows[id]=nil
            elseif row.enabled_frame~=frame_token then
                local ok,why=pcall(sr.Light.set_enabled,row.target_light,true)
                if not ok then
                    destroy(row,live(self.world));self.rows[id]=nil
                    self.retry_at=(now or 0)+1
                    self.status='native light unavailable: keepalive failed: '..tostring(why)
                else row.enabled_frame=frame_token end
            end
        end
        local n=0;for _ in pairs(self.rows) do n=n+1 end;self.count=n
        if n==0 and not next(impacts) then self.status='idle' end
        return n>0,self.status,n
    end
    return self
end
return P
