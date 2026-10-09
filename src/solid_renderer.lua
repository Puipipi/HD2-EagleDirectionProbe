-- HD2-Addon: mods/codex/eagle_solid_renderer
-- Retained world-GUI triangle renderer. Experimental: mission validation pending.
-- HD2 bindings audited offline: creation swaps Y/Z; update passes XYZ unchanged.
-- Uses engine Lua bindings only. No gameplay writes, memory access or Runtime.
local R={}

local function live(sr,world)
    if world==nil then return false end
    local ok,worlds=pcall(sr.Application.worlds)
    if not ok or type(worlds)~='table' then return false end
    for _,w in pairs(worlds) do if w==world then return true end end
    return false
end

local function point(p)
    if type(p)~='table' then return false end
    for i=1,3 do
        local n=p[i]
        if type(n)~='number' or n~=n or math.abs(n)>1e7 then return false end
    end
    return true
end

function R.new(sr)
    if type(sr)~='table' or not sr.Vector3 or not sr.World or not sr.Gui
        or not sr.Application or type(sr.Application.worlds)~='function'
        or not sr.Matrix4x4 or type(sr.Matrix4x4.identity)~='function' then
        return nil,'world triangle API unavailable'
    end
    for _,name in ipairs({'create_world_gui','destroy_gui'}) do
        if type(sr.World[name])~='function' then return nil,'World.'..name..' unavailable' end
    end
    for _,name in ipairs({'triangle','update_triangle','destroy_triangle'}) do
        if type(sr.Gui[name])~='function' then return nil,'Gui.'..name..' unavailable' end
    end
    local self={ids={},status='ready',count=0}

    function self:clear()
        if self.gui and #self.ids>0 and live(sr,self.world) then
            for _,id in ipairs(self.ids) do sr.Gui.destroy_triangle(self.gui,id) end
        end
        self.ids,self.count,self.static,self.flow={},0,nil,nil
    end

    function self:release()
        -- Worlds can disappear before the Lua shutdown hook. Never call a native
        -- destructor through a world/GUI handle that no longer belongs to the engine.
        if self.gui and live(sr,self.world) then sr.World.destroy_gui(self.world,self.gui) end
        self.ids,self.count,self.static,self.flow={},0,nil,nil
        self.gui,self.world=nil,nil
    end

    function self:submit(world,static,flow,colors)
        if not live(sr,world) then self:release();return false,'world unavailable' end
        -- Validate every face before crossing the native boundary.
        local total=0
        for _,batch in ipairs({static,flow}) do
            for _,s in ipairs(batch) do
                if s[4] then
                    if not point(s[2]) or not point(s[3]) or not point(s[4]) or not colors[s[1]] then
                        return false,'invalid face/color'
                    end
                    total=total+2
                end
            end
        end
        if total==0 then self:clear();return true,0 end
        if self.world~=world then self:release() end
        if not self.gui then
            local pose=sr.Matrix4x4.identity()
            if not pose then return false,'identity matrix unavailable' end
            -- Audited args 1=world, 2=pose, 3/4=scale. Retained mode by default.
            self.gui=sr.World.create_world_gui(world,pose,1,1)
            if not self.gui then return false,'world GUI unavailable' end
            self.world=world
        end
        if self.static==static and self.flow==flow then return true,self.count end
        local index=0
        local function face(a,b,c,color)
            index=index+1
            local id=self.ids[index]
            if id~=nil then
                sr.Gui.update_triangle(self.gui,id,
                    sr.Vector3(a[1],a[2],a[3]),sr.Vector3(b[1],b[2],b[3]),
                    sr.Vector3(c[1],c[2],c[3]),100,color)
            else
                -- Compensate the HD2 creation binding's axis swap. Native objects
                -- are made in this submitting frame and never cached in Lua.
                id=sr.Gui.triangle(self.gui,
                    sr.Vector3(a[1],a[3],a[2]),sr.Vector3(b[1],b[3],b[2]),
                    sr.Vector3(c[1],c[3],c[2]),100,color)
                assert(type(id)=='number' and id>=0 and id%1==0,'triangle returned invalid ID')
                self.ids[index]=id
            end
        end
        for _,batch in ipairs({static,flow}) do
            for _,s in ipairs(batch) do
                if s[4] then
                    local color=colors[s[1]]
                    face(s[2],s[3],s[4],color)
                    face(s[2],s[4],s[3],color)
                end
            end
        end
        for i=#self.ids,index+1,-1 do
            sr.Gui.destroy_triangle(self.gui,self.ids[i]);self.ids[i]=nil
        end
        self.static,self.flow,self.count=static,flow,index
        self.status='world triangles (experimental)'
        return true,index
    end
    return self
end
return R
