-- HD2-Addon: mods/codex/eagle_terrain_query
-- Independent read-only vertical collision query. No HD2Runtime; no memory writes.
-- ABI and world/preset checks are evidenced by the installed BTO ground query.
-- Contract fingerprints are derived from the matching decoded game-code snapshot.
-- Native faults cannot be caught by pcall: every precondition precedes the call.
local T = {}
local function finite(n)
    return type(n) == 'number' and n == n and n > -math.huge and n < math.huge
end
local function u32(s, at)
    local a,b,c,d = s:byte(at+1,at+4)
    assert(d, 'short integer')
    return a+b*256+c*65536+d*16777216
end
local function fingerprints(s)
    local a,b,h = 1,0,5381
    for i=1,#s do
        local v=s:byte(i)
        a=(a+v)%65521; b=(b+a)%65521; h=(h*33+v)%4294967296
    end
    return b*65536+a,h
end

local function native_api()
    local ffi = require('ffi')
    assert(ffi.os == 'Windows' and ffi.abi('64bit'), 'Windows x64 required')
    ffi.cdef[[
        void * __stdcall GetModuleHandleA(const char *);
        void * __stdcall GetCurrentProcess(void);
        int __stdcall ReadProcessMemory(void *, const void *, void *, size_t, size_t *);
    ]]
    local k = ffi.load('kernel32')
    local process = k.GetCurrentProcess()
    local buffer,copied = ffi.new('uint8_t[4096]'),ffi.new('size_t[1]')
    local origin,direction,hits = ffi.new('float[3]'),ffi.new('float[3]',{0,0,-1}),ffi.new('float[11]')
    local query,query_address
    return {
        module=function(name)
            return tonumber(ffi.cast('uintptr_t',k.GetModuleHandleA(name)))
        end,
        address=function(value)
            assert(type(value)=='userdata','engine userdata required')
            return tonumber(ffi.cast('uintptr_t',value))
        end,
        read=function(address,length)
            copied[0]=0
            if k.ReadProcessMemory(process,ffi.cast('const void *',address),buffer,length,copied)~=0
                and tonumber(copied[0])==length then return ffi.string(buffer,length) end
        end,
        query=function(address,handle,x,y,z,length,exclude)
            -- The only game function invoked by this module. BTO's existing seven-argument
            -- query wrapper, not the different eleven-argument inner-query ABI.
            if query_address~=address then
                query=ffi.cast('uint32_t (*)(uint32_t,const float *,const float *,float,uint32_t,void *,uint32_t)',address)
                query_address=address
            end
            origin[0],origin[1],origin[2]=x,y,z
            ffi.fill(hits,44)
            local count=tonumber(query(handle,origin,direction,length,exclude,hits,1))
            if count==0 then return 0 end
            local result={}
            for i=0,6 do result[i+1]=tonumber(hits[i]) end
            return count,result
        end
    }
end

function T.new(api, contract)
    -- Injecting a boundary/contract is for offline tests. The packaged caller passes neither.
    local self={status='not checked',casts=0}
    local exe,game,checked_at
    local function read(at,n)
        assert(finite(at) and at>=65536 and at%1==0 and at+n<2^47 and n>0 and n<=4096,
            'invalid memory range')
        local s=api.read(at,n)
        assert(type(s)=='string' and #s==n,'memory unavailable')
        return s
    end
    local function pointer(at)
        local s=read(at,8)
        local p=u32(s,0)+u32(s,4)*4294967296
        assert(p>=65536 and p<2^47 and p%8==0,'invalid pointer')
        return p
    end
    local function verify_code()
        for name,expect in pairs(contract.modules) do
            local base=name=='helldivers2.exe' and exe or game
            local dos=read(base,64)
            assert(dos:sub(1,2)=='MZ','invalid module header')
            local off=u32(dos,0x3c)
            assert(off>=64 and off<1048576,'invalid PE offset')
            local pe=read(base+off,0x58)
            assert(pe:sub(1,4)=='PE\0\0' and pe:byte(5)==100 and pe:byte(6)==134 and
                pe:byte(25)==11 and pe:byte(26)==2 and u32(pe,8)==expect.stamp and
                u32(pe,0x50)==expect.size,'unsupported game build')
        end
        for _,r in ipairs(contract.code) do
            local base=r.module=='helldivers2.exe' and exe or game
            assert(r.rva>=4096 and r.rva+r.size<contract.modules[r.module].size,'code range')
            local a,h=fingerprints(read(base+r.rva,r.size))
            assert(a==r.adler32 and h==r.djb32,'native code changed: '..(r.name or 'query'))
        end
        checked_at=os.clock()
    end
    function self:height(sr,world,unit,x,y,z)
        if self.failed then return nil,self.status end
        local ok,height,status=pcall(function()
            assert(finite(x) and finite(y) and finite(z) and math.abs(x)<1e6 and
                math.abs(y)<1e6 and math.abs(z)<1e5,'invalid sample position')
            if world==nil or unit==nil then return nil,'SOURCE_UNAVAILABLE' end
            local alive_ok,alive=pcall(sr.Unit.alive,unit)
            local world_ok,unit_world=pcall(sr.Unit.world,unit)
            if not alive_ok or not alive or not world_ok or unit_world~=world then
                return nil,'SOURCE_UNAVAILABLE'
            end
            if not api then api=native_api() end
            if not contract then contract=require('mods/codex/eagle_terrain_contract') end
            if not exe then
                exe,game=api.module('helldivers2.exe'),api.module('game.dll')
                assert(finite(exe) and exe>=65536 and finite(game) and game>=65536,'game modules unavailable')
            end
            if not checked_at or os.clock()-checked_at>=1 then verify_code() end
            local l=contract.layout
            local wp=pointer(api.address(world))
            local tagged=api.address(unit)
            assert(finite(tagged) and tagged>=1 and tagged<2^32 and tagged%4==1,'invalid unit handle')
            local set=pointer(pointer(game+l.owner)+8)
            assert(pointer(set)==wp,'query world mismatch')
            local handle=u32(read(set+0xa0,4),0)
            assert(handle>=0x80000000 and handle<0x80000100 and
                u32(read(set+0x1c,4),0)==handle,'invalid query handle')
            local preset=read(exe+l.presets+(handle-0x80000000)*20,20)
            local wi=u32(preset,0)
            assert(wi<4 and u32(preset,4)==2 and u32(preset,8)==5 and
                u32(preset,12)==0x3e24ec53 and u32(preset,16)==0x80000009,'query preset mismatch')
            assert(pointer(exe+l.worlds+wi*8)==wp,'physics world mismatch')
            local address=pointer(pointer(game+l.api)+0x68)
            assert(address==exe+l.query,'query function mismatch')
            self.casts=self.casts+1
            local count,hit=api.query(address,handle,x,y,z+160,320,(tagged-1)/4)
            assert(finite(count) and count>=0 and count<2^32 and count%1==0,'invalid hit count')
            if count==0 then return nil,'MISS' end
            assert(type(hit)=='table','hit unavailable')
            for i=1,7 do assert(finite(hit[i]),'nonfinite hit') end
            assert(math.abs(hit[1]-x)<=0.5 and math.abs(hit[2]-y)<=0.5 and
                hit[3]>=z-160 and hit[3]<=z+160 and hit[7]>=0 and hit[7]<=320 and
                math.abs((z+160-hit[3])-hit[7])<=0.5,'hit outside vertical segment')
            if hit[6]<0.2 then return nil,'MISS' end
            return hit[3],'HIT'
        end)
        if not ok then
            self.status='UNAVAILABLE: '..tostring(height):gsub('^.-:%d+: ',''):sub(1,140)
            -- Fail closed for this provider instance. The caller may create a fresh instance
            -- after a delay (e.g. world transition), never retry a failed call in a tight loop.
            self.failed=true
            return nil,self.status
        end
        self.status=status
        return height,status
    end
    return self
end
return T
