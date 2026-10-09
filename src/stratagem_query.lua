-- HD2-Addon: mods/codex/eagle_stratagem_query
-- Independent, bounded current-process record reader. No Runtime or game calls.
-- Layout evidence: user-supplied Eagle HUD Reference 1.1.1, matching disk builds.
local Q={}
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<2^47 end
local function u32(s,o)
    local a,b,c,d=s:byte(o+1,o+4);assert(d,'short integer')
    return a+b*256+c*65536+d*16777216
end
local function ptr(s,o)
    local p=u32(s,o)+u32(s,o+4)*4294967296
    assert(p>=65536 and p<2^47 and p%8==0,'invalid pointer')
    return p
end
local function f32(s,o)
    local v=u32(s,o);local e=math.floor(v/8388608)%256;local m=v%8388608
    assert(e~=255,'nonfinite coordinate')
    local n=e==0 and m*2^-149 or (1+m/8388608)*2^(e-127)
    if v>=2147483648 then n=-n end
    assert(math.abs(n)<=100000,'coordinate out of bounds')
    return n
end
local function digest(s)
    local a,b,h=1,0,5381
    for i=1,#s do local v=s:byte(i);a=(a+v)%65521;b=(b+a)%65521;h=(h*33+v)%4294967296 end
    return b*65536+a,h
end
local function live(sr,world)
    if not world or not sr or not sr.Application then return false end
    local app=sr.Application
    if type(app.main_world)~='function' or type(app.worlds)~='function' or app.main_world()~=world then return false end
    local worlds=app.worlds()
    if type(worlds)~='table' then return false end
    for _,w in pairs(worlds) do if w==world then return true end end
    return false
end

local function native_api()
    local ffi=require('ffi')
    assert(ffi.os=='Windows' and ffi.abi('64bit'),'Windows x64 required')
    ffi.cdef[[
        void * __stdcall GetModuleHandleA(const char *);
        void * __stdcall GetCurrentProcess(void);
        int __stdcall ReadProcessMemory(void *, const void *, void *, size_t, size_t *);
    ]]
    local k=ffi.load('kernel32')
    local process=k.GetCurrentProcess()
    local buffer,copied=ffi.new('uint8_t[65536]'),ffi.new('size_t[1]')
    return {module=function(name) return tonumber(ffi.cast('uintptr_t',k.GetModuleHandleA(name))) end,
        read=function(at,n)
            if n<1 or n>65536 then return nil end
            copied[0]=0
            if k.ReadProcessMemory(process,ffi.cast('const void *',at),buffer,n,copied)~=0
                and tonumber(copied[0])==n then return ffi.string(buffer,n) end
        end}
end

function Q.new(api,contract)
    local self={status='not checked',snapshots=0}
    local exe,game,checked
    local function read(at,n)
        assert(finite(at) and at>=65536 and at%1==0 and at+n<2^47 and n>0 and n<=65536,'invalid read range')
        local s=api.read(at,n)
        assert(type(s)=='string' and #s==n,'unreadable or short snapshot')
        return s
    end
    local function pointer(at) return ptr(read(at,8),0) end
    local function verify()
        for name,expected in pairs(contract.modules) do
            local base=name=='helldivers2.exe' and exe or game
            local dos=read(base,64);assert(dos:sub(1,2)=='MZ','invalid DOS header')
            local off=u32(dos,60);assert(off>=64 and off<1048576,'invalid PE offset')
            local pe=read(base+off,88)
            assert(pe:sub(1,4)=='PE\0\0' and pe:byte(5)==100 and pe:byte(6)==134
                and pe:byte(25)==11 and pe:byte(26)==2 and u32(pe,8)==expected.stamp
                and u32(pe,80)==expected.size,'unsupported game build')
        end
        assert(contract.modules['game.dll'].size>0x33266b8,'active record RVA outside module')
        for _,code in ipairs(contract.code) do
            local base=code.module=='helldivers2.exe' and exe or game
            assert(code.rva>=4096 and code.rva+code.size<contract.modules[code.module].size,'code range')
            local a,h=digest(read(base+code.rva,code.size))
            assert(a==code.adler32 and h==code.djb32,'code fingerprint changed')
        end
        checked=os.clock()
    end
    local function mission()
        local object=pointer(game+0x3326340)
        if u32(read(object+705052,4),0)~=4 then return nil end
        local mode=pointer(game+0x33266a0)
        local header=read(mode,68)
        if u32(header,8)~=1 then return nil end
        local descriptor=ptr(header,56)
        local entity=u32(read(descriptor,24),8)
        return tostring(mode)..':'..tostring(descriptor)..':'..entity
    end
    function self:snapshot(sr,world)
        if self.failed then return nil,self.status end
        local ok,rows,status,key=pcall(function()
            if not live(sr,world) then return nil,'WORLD_UNAVAILABLE' end
            if not api then api=native_api() end
            if not contract then contract=require('mods/codex/eagle_terrain_contract') end
            local e,g=api.module('helldivers2.exe'),api.module('game.dll')
            assert(finite(e) and e>=65536 and finite(g) and g>=65536,'game modules unavailable')
            if exe~=e or game~=g then checked=nil end
            exe,game=e,g
            if not checked or os.clock()-checked>=1 then verify() end
            local epoch=mission()
            if not epoch then return {},'NOT_MISSION' end
            local manager=pointer(game+0x33266b0)
            local header=read(manager,128)
            local count=u32(header,0x34)
            assert(count<=512,'active record count out of bounds')
            local array=count>0 and ptr(header,0x78) or nil
            local data=count>0 and read(array,count*64) or ''
            local after=read(manager,128)
            assert(u32(after,0x34)==count and (count==0 or ptr(after,0x78)==array)
                and pointer(game+0x33266b0)==manager,'active header changed during copy')
            assert(mission()==epoch and live(sr,world),'mission/world changed during copy')
            local result={}
            for i=0,count-1 do
                local offset=i*64;local id=u32(data,offset+12)
                -- Keep unsupported types as ambiguity blockers; profiles assign known types only.
                result[#result+1]={type=id,
                    p={f32(data,offset+16),f32(data,offset+20),f32(data,offset+24)},
                    anchor={f32(data,offset+48),f32(data,offset+52),f32(data,offset+56)}}
            end
            self.snapshots=self.snapshots+1
            return result,'READY',epoch
        end)
        if not ok then
            self.failed=true;self.status='UNAVAILABLE: '..tostring(rows):gsub('^.-:%d+: ',''):sub(1,160)
            return nil,self.status
        end
        self.status=status
        return rows,status,key
    end
    return self
end
return Q
