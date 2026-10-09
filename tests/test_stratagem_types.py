"""Conservative per-ball type association and explicitly estimated reference footprints."""
import unittest
from pathlib import Path
from lupa.luajit21 import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]


class StratagemTypesTest(unittest.TestCase):
    def run_lua(self,script):
        self.assertTrue((ROOT/'src/stratagem_profiles.lua').exists(),'type association feature missing')
        lua=LuaRuntime()
        lua.globals().path=str(ROOT/'src/stratagem_profiles.lua')
        lua.execute("local P=assert(loadfile(path))()\n"+script)

    def test_eight_types_and_reference_bounds_keep_targeted_rockets_unknown(self):
        self.run_lua('''
local ids={3,18,30,38,65,126,133,140}
for _,id in ipairs(ids) do assert(P.catalog[id] and P.catalog[id].tag) end
local a,s,k,r,n=P.bounds(18),P.bounds(30),P.bounds(3),P.bounds(140),P.bounds(133)
assert(a.lo==-100/3 and a.hi==100/3 and a.half==10 and a.estimated)
assert(s.lo==-5 and s.hi==55 and s.half==5)
assert(k.shape=='circle' and k.radius==25 and k.estimated)
assert(r.shape=='direction' and not r.estimated,'110mm invented a target footprint')
assert(n.lo==-100/3 and n.hi==100/3 and n.half==10 and n.estimated,
    'Napalm should use the user-calibrated 66.67 m envelope while preserving width')
for _,id in ipairs({18,65,133,38,126}) do
    local b=P.bounds(id)
    assert(b.lo==-100/3 and b.hi==100/3 and b.half==10,
        'broad transverse Eagle references should share the user-selected envelope')
end
assert(P.bounds(nil).lo==-100 and P.bounds(999).half==6)
''')

    def test_two_consistent_snapshots_are_required_and_aircraft_heading_is_untouched(self):
        self.run_lua('''
local h={0,1,0};local imp={p={20,30,0},heading=h}
local rows={{type=18,p={20.1,30,0},anchor={0,0,0}}}
assert(P.associate({imp},rows,1,'mission')==0 and not imp.stratagem_type)
assert(P.associate({imp},rows,1.05,'mission')==0)
assert(P.associate({imp},rows,1.2,'mission')==1 and imp.stratagem_type==18)
assert(imp.heading==h and h[1]==0 and h[2]==1,'throw anchor replaced actual flight direction')
assert(P.associate({imp},{},2,'mission')==0 and imp.stratagem_type==18,
    'lost native row changed guide lifetime or cleared a locked label')
''')

    def test_squad_calls_and_more_than_sixteen_guides_are_not_capped(self):
        self.run_lua('''
local imps,rows={},{}
for i=1,24 do
    imps[i]={p={i*20,0,0}}
    rows[i]={type=i%2==0 and 65 or 18,p={i*20,0,0}}
end
P.associate(imps,rows,1,'m')
assert(P.associate(imps,rows,1.2,'m')==24)
for i=1,24 do assert(imps[i].stratagem_type==rows[i].type) end
''')

    def test_one_row_shared_by_two_balls_and_two_rows_at_one_ball_stay_unknown(self):
        self.run_lua('''
local a,b={p={0,0,0}},{p={1,0,0}}
local rows={{type=18,p={0,0,0}}}
P.associate({a,b},rows,1,'m');P.associate({a,b},rows,2,'m')
assert(not a.stratagem_type and not b.stratagem_type)
rows[2]={type=65,p={0.1,0,0}}
P.associate({a},rows,3,'m');P.associate({a},rows,4,'m')
assert(not a.stratagem_type,'ambiguous nearby calls were guessed')
''')

    def test_world_change_invalidates_old_labels_and_new_ball_does_not_inherit(self):
        self.run_lua('''
local imp={p={0,0,0}};local rows={{type=3,p={0,0,0}}}
P.associate({imp},rows,1,'old');P.associate({imp},rows,1.2,'old')
assert(imp.stratagem_type==3)
P.associate({imp},{},2,'new')
assert(not imp.stratagem_type,'old mission label survived epoch change')
local new={p={0,0,0}}
P.associate({new},{{type=65,p={0,0,0}}},3,'new')
assert(not new.stratagem_type,'a fresh throw inherited an old match')
''')

    def test_unknown_types_and_unavailable_snapshots_clear_pending_matches(self):
        self.run_lua('''
local imp={p={0,0,0}};local rows={{type=18,p={0,0,0}}}
P.associate({imp},rows,1,'m');P.associate({imp},nil,1.1,'m')
assert(P.associate({imp},rows,1.2,'m')==0 and not imp.stratagem_type)
P.associate({imp},{{type=999,p={0,0,0}}},2,'m')
assert(not imp.stratagem_type)
''')

    def test_unsupported_records_block_ambiguous_eagle_association(self):
        self.run_lua('''
local imp={p={0,0,0}}
local rows={{type=18,p={0,0,0}},{type=999,p={0.1,0,0}}}
P.associate({imp},rows,1,'m');P.associate({imp},rows,1.2,'m')
assert(not imp.stratagem_type,'unsupported nearby record was ignored as an ambiguity blocker')
rows[1]=rows[2];rows[2]=nil
P.associate({imp},rows,2,'m');P.associate({imp},rows,2.2,'m')
assert(not imp.stratagem_type,'unsupported type was assigned')
''')


if __name__=='__main__': unittest.main()
