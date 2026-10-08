"""Beacon ownership regressions for intermittent corridor displacement and disappearance."""
import unittest

from test_mission_feedback import replay, THROW


class AlignmentFeedbackTest(unittest.TestCase):
    def test_four_teammate_beacons_landing_together_keep_four_corridors(self):
        replay('''
local balls,positions={},{}
for i=1,4 do balls[i]={}; positions[balls[i]]={i*300,100,40} end
local query,position=sr.World.units_by_resource,sr.Unit.world_position
sr.World.units_by_resource=function(world,key)
    if key=='16f397ca5f51f271' then return balls end
    return query(world,key)
end
sr.Unit.world_position=function(unit)
    return positions[unit] or position(unit)
end
M.tracks={design={trail={{0,0,80}},heading={1,0,0},seen=FAKE_TIME+1000}}
tick(5)
for i,ball in ipairs(balls) do positions[ball]={i*300+100,100,10} end
tick(30)
local count=0
for _,imp in pairs(M.impacts) do
    count=count+1
    local expected=positions[imp.beacon]
    assert(expected and imp.p[1]==expected[1] and imp.p[2]==expected[2],
        'a teammate corridor took another beacon position')
end
assert(count==4,'four teammates landing together must retain four corridors')
''')

    def test_registered_aircraft_without_beacons_still_get_independent_air_guides(self):
        replay('''
local planes,positions={},{}
for i=1,4 do planes[i]={}; positions[planes[i]]={i*300,0,500} end
local query,position=sr.World.units_by_resource,sr.Unit.world_position
sr.World.units_by_resource=function(world,key)
    if key=='content/fac_helldivers/vehicles/eagle/eagle' then return planes end
    if key=='16f397ca5f51f271' then return {} end
    return query(world,key)
end
sr.Unit.world_position=function(unit) return positions[unit] or position(unit) end
tick(10)
local count=0
for _,plane in ipairs(planes) do
    local track=M.tracks[plane]
    assert(track and not track.finished and track.heading,'unbeaconed aircraft was lost')
    count=count+1
end
assert(count==4 and #M.seg>100,'independent aircraft guides were not drawn')
assert(next(M.impacts)==nil,'aircraft alone must not invent a beacon landing point')
''')

    def test_new_throw_does_not_reuse_an_older_settled_beacon(self):
        replay(THROW + '''
local other={}
local p={400,100,50}
local query,position=sr.World.units_by_resource,sr.Unit.world_position
sr.World.units_by_resource=function(world,key)
    if key=='16f397ca5f51f271' then return {BEACON,other} end
    return query(world,key)
end
sr.Unit.world_position=function(unit)
    if unit==other then return p end
    return position(unit)
end
tick(5)
p={500,100,20}
tick(5)
tick(10)
local found=false
for _,imp in pairs(M.impacts) do
    if imp.beacon==other then
        found=true
        assert(math.abs(imp.p[1]-500)<0.1 and math.abs(imp.p[2]-100)<0.1,
            'new warning moved to the wrong beacon')
    end
end
assert(found,'older thrown beacon swallowed the new landing point')
''')

    def test_two_simultaneous_landings_both_get_their_actual_locations(self):
        replay('''
local one,two={},{}
local a,b={0,0,40},{300,100,40}
local query,position=sr.World.units_by_resource,sr.Unit.world_position
sr.World.units_by_resource=function(world,key)
    if key=='16f397ca5f51f271' then return {one,two} end
    return query(world,key)
end
sr.Unit.world_position=function(unit)
    if unit==one then return a end
    if unit==two then return b end
    return position(unit)
end
M.tracks={design={trail={{0,0,80}},heading={1,0,0},seen=FAKE_TIME+1000}}
tick(5)
a,b={100,0,10},{400,100,10}
tick(30)
local found1,found2=false,false
for _,imp in pairs(M.impacts) do
    if imp.beacon==one then found1=imp.p[1]==100 and imp.p[2]==0 end
    if imp.beacon==two then found2=imp.p[1]==400 and imp.p[2]==100 end
end
assert(found1 and found2,'simultaneous beacons lost a corridor or shared a landing point')
''')

if __name__=='__main__':
    unittest.main()
