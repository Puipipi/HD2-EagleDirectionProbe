"""Unknown native beacon candidates must not become Eagle ground corridors."""
import unittest
from test_mission_feedback import replay, THROW
from test_type_display import FLAT, TYPES
from test_native_light_probe import NATIVE
from test_departure_options_performance import MENU


class BlueBeaconDiagnosticTest(unittest.TestCase):
    def test_unconfirmed_support_beacon_then_eagle_draws_only_eagle(self):
        replay(TYPES+FLAT+MENU+NATIVE+"saved['eagle_direction_probe.show_native_light_probe']=true\n"+'''
local blue,blue_active={},true
local bluep={0,0,40}
type_rows={{type=9001,p={0,0,40},anchor={0,100,40}}}
local query,position=sr.World.units_by_resource,sr.Unit.world_position
sr.World.units_by_resource=function(world,key)
    if key=='16f397ca5f51f271' then
        local units={}
        if blue_active then units[#units+1]=blue end
        if ST.beacon_arc>0 then units[#units+1]=BEACON end
        return units
    end
    return query(world,key)
end
sr.Unit.world_position=function(unit,...)
    if unit==blue then return {bluep[1],bluep[2],bluep[3]} end
    return position(unit,...)
end

-- A blue support beacon is observed, moves, and settles before the Eagle is thrown.
tick(1)
bluep={12,8,38};tick(1)
bluep={24,16,36};tick(1)
bluep={80,20,32};tick(60)
local blueid=next(M.impacts)
assert(blueid and M.impacts[blueid].stratagem_type==nil,
    'unsupported support type must remain an unconfirmed candidate')
assert(spawned==0 and live_count()==0,
    'unconfirmed support beacon spawned a native Eagle light before the Eagle was thrown')
local blue_landed={bluep[1],bluep[2],bluep[3]}
type_rows={{type=9001,p=blue_landed,anchor={80,120,32}}}

-- Then throw a positively catalogued Eagle beacon while the blue beacon remains.
ST.aircraft_up=true
ST.beacon_arc=1;tick(4)
ST.beacon_arc=5;tick(60)
type_rows={
    {type=9001,p=blue_landed,anchor={80,120,32}},
    {type=18,p={48,32,32},anchor={48,132,32}},
}
frames(50)
local eagle
for id,imp in pairs(M.impacts) do if id~=blueid then eagle=id end end
assert(M.impacts[blueid] and eagle and M.impacts[blueid].stratagem_type==nil,
    'unconfirmed support candidate was lost or classified as Eagle')
assert(M.impacts[eagle].stratagem_type==18,'known Eagle did not reach positive confirmation')
assert(not M.impacts[blueid].heading and not M.impacts[blueid].aircraft,
    'unconfirmed support candidate acquired an Eagle approach axis')
local centers={}
for _,s in ipairs(M.seg) do if s[1]=='marker' then
    local x,count=0,0
    for i=2,#s do if type(s[i])=='table' and type(s[i][1])=='number' then
        x=x+s[i][1];count=count+1
    end end
    x=x/math.max(1,count)
    if math.abs(x-48)<5 then centers.eagle=true end
    if math.abs(x-80)<5 then centers.blue=true end
end end
assert(centers.eagle and not centers.blue,
    'only the positively confirmed Eagle may draw a landing marker / corridor')
assert(#M.track_order>0 and FRAME_HAS_LINES,'unconfirmed ground candidate hid the aircraft arrow')
assert(live_count()==1 and M.native_light_count==1,
    'native helper must belong only to the confirmed Eagle guide')
assert(spawned==1,'support candidate created an extra native helper or guide recreation')
''')

    def test_reader_unavailable_keeps_candidate_and_aircraft_arrow_without_ground_guide(self):
        replay(TYPES+FLAT+'''type_rows=nil
'''+THROW+'''
frames(20)
local markers,ground=0,0
for _,s in ipairs(M.seg) do
    if s[1]=='marker' then markers=markers+1 end
    if s[1]=='ground' then ground=ground+1 end
end
assert(next(M.impacts)~=nil,'unclassified beacon candidate was discarded')
assert(markers==0 and ground==0,'reader-unavailable candidate drew an Eagle corridor')
assert(#M.track_order>0 and FRAME_HAS_LINES,'unclassified candidate hid the aircraft arrow')
''')

    def test_multiple_positive_eagle_records_each_get_a_corridor(self):
        replay(TYPES+FLAT+THROW+'''
local eagle=next(M.impacts)
M.impacts[203]={p={1500,0,0},heading={1,0,0},t=FAKE_TIME,born=FAKE_TIME}
type_rows={
    {type=18,p={48,32,32},anchor={48,132,32}},
    {type=18,p={1500,0,0},anchor={1500,100,0}},
}
frames(50)
assert(M.impacts[eagle].stratagem_type==18 and M.impacts[203].stratagem_type==18,
    'both distinct Eagle records need positive association')
local centers={}
for _,s in ipairs(M.seg) do if s[1]=='marker' then
    local x,count=0,0
    for i=2,#s do if type(s[i])=='table' and type(s[i][1])=='number' then
        x=x+s[i][1];count=count+1
    end end
    x=x/math.max(1,count)
    if math.abs(x-48)<5 then centers[1]=true end
    if math.abs(x-1500)<5 then centers[2]=true end
end end
assert(centers[1] and centers[2],'positive guide filtering imposed a guide-count cap')
''')


if __name__ == '__main__':
    unittest.main()
