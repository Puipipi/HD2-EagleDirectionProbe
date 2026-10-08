"""Native boundary guards: no real game functions run in this test suite."""
import struct
import unittest
import zlib
from pathlib import Path

from lupa.luajit21 import LuaRuntime

MODULE = Path(__file__).resolve().parents[1]/'src/terrain_query.lua'


class NativeTerrainTest(unittest.TestCase):
    def run_boundary(self, mutation='', assertion='assert(z==12 and status=="HIT" and calls==1)'):
        lua = LuaRuntime(encoding=None)
        lua.globals()[b'module_path'] = str(MODULE).encode()
        lua.execute(b'''
local factory=assert(loadfile(module_path))()
local function u32(n)
    local b={}
    for i=1,4 do b[i]=string.char(n%256); n=math.floor(n/256) end
    return table.concat(b)
end
local function ptr(n) return u32(n)..u32(0) end
local function header(stamp,size)
    local s='PE\0\0'..string.char(100,134,1,0)..u32(stamp)..string.rep('\0',12)
    s=s..string.char(11,2)..string.rep('\0',54)..u32(size)..string.rep('\0',4)
    return s
end
local exe,game=0x100000,0x200000
local code='abcd'
local contract={modules={['helldivers2.exe']={stamp=1,size=0x10000},
    ['game.dll']={stamp=2,size=0x10000}},
    code={{module='helldivers2.exe',rva=0x1100,size=4,adler32=64487819,djb32=2090069583}},
    layout={owner=0x200,api=0x208,presets=0x300,worlds=0x400,query=0x1100}}
local memory={}
memory[exe]='MZ'..string.rep('\0',58)..u32(64)
memory[game]=memory[exe]
memory[exe+64]=header(1,0x10000)
memory[game+64]=header(2,0x10000)
memory[exe+0x1100]=code
local world,unit={},{}
local addresses={[world]=0x300000,[unit]=401}
local worldptr=0x310000
memory[0x300000]=ptr(worldptr)
memory[game+0x200]=ptr(0x400000)
memory[0x400008]=ptr(0x410000)
memory[0x410000]=ptr(worldptr)
memory[0x4100a0]=u32(0x80000000)
memory[0x41001c]=u32(0x80000000)
memory[exe+0x300]=u32(0)..u32(2)..u32(5)..u32(0x3e24ec53)..u32(0x80000009)
memory[exe+0x400]=ptr(worldptr)
memory[game+0x208]=ptr(0x420000)
memory[0x420068]=ptr(exe+0x1100)
local calls=0
local api={module=function(name) return name=='helldivers2.exe' and exe or game end,
    read=function(at,n) local s=memory[at]; return s and s:sub(1,n) end,
    address=function(v) return addresses[v] end,
    query=function(at,handle,x,y,z,length,exclude)
        calls=calls+1
        assert(at==exe+0x1100 and handle==0x80000000 and exclude==100)
        return 1,{x,y,12,0,0,1,z-12}
    end}
local sr={Unit={alive=function() return true end,world=function() return world end}}
''' + mutation.encode() + b'''
local q=factory.new(api,contract)
local z,status=q:height(sr,world,unit,20,30,10)
''' + assertion.encode())

    def test_valid_world_and_code_reach_the_collision_boundary(self):
        self.run_boundary()

    def test_changed_native_code_is_rejected_before_call(self):
        self.run_boundary("memory[exe+0x1100]='abce'", 'assert(z==nil and calls==0 and status:find("UNAVAILABLE"))')

    def test_changed_build_is_rejected_before_call(self):
        self.run_boundary('memory[game+64]=header(3,0x10000)', 'assert(z==nil and calls==0)')

    def test_wrong_world_is_rejected_before_call(self):
        self.run_boundary('memory[0x410000]=ptr(worldptr+8)', 'assert(z==nil and calls==0)')

    def test_wrong_collision_preset_is_rejected_before_call(self):
        self.run_boundary("memory[exe+0x300]=string.rep('x',20)", 'assert(z==nil and calls==0)')

    def test_dead_source_unit_is_rejected_before_call(self):
        self.run_boundary('sr.Unit.alive=function() return false end', 'assert(z==nil and calls==0)')

    def test_one_dead_source_does_not_disable_other_live_sources(self):
        self.run_boundary('sr.Unit.alive=function() return false end', '''
assert(z==nil and calls==0)
sr.Unit.alive=function() return true end
local recovered=q:height(sr,world,unit,20,30,10)
assert(recovered==12 and calls==1,'dead source disabled the shared provider')
''')

    def test_miss_and_malformed_hit_are_not_heights(self):
        for result in ['return 0', 'return 1,{20,30,0/0,0,0,1,10}',
                       'return 1,{20,30,99999,0,0,1,10}', 'return 1,{20,30,12,0,0,-1,158}']:
            with self.subTest(result=result):
                self.run_boundary('api.query=function() calls=calls+1; '+result+' end',
                                  'assert(z==nil and calls==1)')

    def test_production_boundary_fails_closed_outside_the_game(self):
        lua=LuaRuntime()
        lua.globals().path=str(MODULE)
        lua.globals().contract_path=str(MODULE.with_name('terrain_contract.lua'))
        lua.execute('''
local factory=assert(loadfile(path))()
package.preload['mods/codex/eagle_terrain_contract']=assert(loadfile(contract_path))
local world,unit={},{}
local sr={Unit={alive=function() return true end,world=function() return world end}}
local q=factory.new()
local z,status=q:height(sr,world,unit,20,30,10)
assert(z==nil and q.casts==0 and status:find('UNAVAILABLE'),
    'production boundary must not call game code outside the game')
''')


if __name__ == '__main__':
    unittest.main()
