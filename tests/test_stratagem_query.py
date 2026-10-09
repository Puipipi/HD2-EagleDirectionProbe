"""Native record reader uses only injected bytes; no game process is opened."""
import unittest
from pathlib import Path
from lupa.luajit21 import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
SETUP=r'''
local Q=assert(loadfile(query_path))()
local function u32(n)
    local b={};for i=1,4 do b[i]=string.char(n%256);n=math.floor(n/256) end
    return table.concat(b)
end
local function ptr(n) return u32(n)..u32(0) end
local function put(s,o,v) return s:sub(1,o)..v..s:sub(o+#v+1) end
local function pe(stamp)
    local s=string.rep('\0',88)
    s=put(s,0,'PE\0\0');s=put(s,4,string.char(100,134));s=put(s,8,u32(stamp))
    s=put(s,24,string.char(11,2));return put(s,80,u32(0x5000000))
end
local exe,game=0x1000000,0x2000000
local object,mode,descriptor,manager,array=0x10000000,0x11000000,0x12000000,0x13000000,0x14000000
local mem={}
mem[exe]='MZ'..string.rep('\0',58)..u32(64);mem[game]=mem[exe]
mem[exe+64]=pe(1);mem[game+64]=pe(2);mem[exe+0x1100]='abcd'
mem[game+0x3326340]=ptr(object);mem[object+705052]=u32(4)
mem[game+0x33266a0]=ptr(mode)
mem[mode]=put(put(string.rep('\0',68),8,u32(1)),56,ptr(descriptor))
mem[descriptor]=put(string.rep('\0',24),8,u32(7))
mem[game+0x33266b0]=ptr(manager)
mem[manager]=put(put(string.rep('\0',128),0x34,u32(1)),0x78,ptr(array))
local row=put(string.rep('\0',64),12,u32(18))
row=put(put(put(row,16,u32(0x41a00000)),20,u32(0x41f00000)),24,u32(0x41200000)) -- 20,30,10
mem[array]=row
local reads,bulk,module_calls=0,0,0
local api={module=function(name) module_calls=module_calls+1;return name=='helldivers2.exe' and exe or game end,
    read=function(at,n)
        reads=reads+1;if at==array then bulk=bulk+1 end
        local s=mem[at];return s and s:sub(1,n)
    end}
local contract={modules={['helldivers2.exe']={stamp=1,size=0x5000000},['game.dll']={stamp=2,size=0x5000000}},
    code={{module='helldivers2.exe',rva=0x1100,size=4,adler32=64487819,djb32=2090069583}}}
local world={}
local sr={Application={main_world=function() return world end,worlds=function() return {world} end}}
'''


class StratagemQueryTest(unittest.TestCase):
    def boundary(self,mutation='',check="assert(rows and #rows==1 and rows[1].type==18 and rows[1].p[1]==20 and rows[1].p[2]==30 and rows[1].p[3]==10 and key and bulk==1)"):
        self.assertTrue((ROOT/'src/stratagem_query.lua').exists(),'read-only active-record query missing')
        lua=LuaRuntime(encoding=None)
        lua.globals()[b'query_path']=str(ROOT/'src/stratagem_query.lua').encode()
        lua.execute(SETUP.encode()+mutation.encode()+b'''
local q=Q.new(api,contract)
assert(module_calls==0,'module load/constructor performed native reads')
local rows,status,key=q:snapshot(sr,world)
'''+check.encode())

    def test_valid_record_and_coordinates(self): self.boundary()

    def test_unsupported_rows_are_preserved_for_spatial_ambiguity_checks(self):
        self.boundary("mem[manager]=put(mem[manager],0x34,u32(2));mem[array]=row..put(row,12,u32(999))",
                      "assert(rows and #rows==2 and rows[2].type==999 and rows[2].p[1]==20)")

    def test_changed_build_and_code_never_read_records(self):
        for mutation in ("mem[game+64]=pe(3)","mem[exe+0x1100]='abce'"):
            with self.subTest(mutation=mutation): self.boundary(mutation,"assert(not rows and bulk==0 and status:find('UNAVAILABLE'))")

    def test_nonmission_or_invalid_world_never_reads_active_array(self):
        for mutation in ("mem[object+705052]=u32(3)","sr.Application.worlds=function() return {} end"):
            with self.subTest(mutation=mutation): self.boundary(mutation,"assert(bulk==0 and (not rows or #rows==0))")

    def test_bad_pointer_count_short_read_and_nonfinite_record_are_rejected(self):
        cases=["mem[manager]=put(mem[manager],0x34,u32(513))",
               "mem[manager]=put(mem[manager],0x78,ptr(3))",
               "mem[array]=row:sub(1,30)",
               "mem[array]=put(row,16,u32(0x7fc00000))"]
        for mutation in cases:
            with self.subTest(mutation=mutation): self.boundary(mutation,"assert(not rows and status:find('UNAVAILABLE'))")

    def test_header_change_during_copy_rejects_torn_snapshot(self):
        self.boundary('''
local read=api.read
api.read=function(at,n)
    local s=read(at,n)
    if at==array then mem[manager]=put(mem[manager],0x34,u32(2)) end
    return s
end
''',"assert(not rows and bulk==1 and status:find('UNAVAILABLE'))")

    def test_more_than_sixteen_records_use_one_bounded_bulk_read(self):
        self.boundary("mem[manager]=put(mem[manager],0x34,u32(24));mem[array]=row:rep(24)",
                      "assert(rows and #rows==24 and bulk==1 and reads<30)")

    def test_missing_native_modules_falls_back(self):
        self.boundary("api.module=function() return nil end","assert(not rows and bulk==0)")


if __name__=='__main__': unittest.main()
