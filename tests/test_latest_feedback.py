"""Captured late throw and the requested filled, moving planar presentation."""
import json
import unittest
from pathlib import Path

from test_mission_feedback import replay, THROW
from test_terrain_query import SCENE


class LatestFeedbackTest(unittest.TestCase):
    def test_captured_pause_then_throw_reaches_its_actual_landing(self):
        data = json.loads((Path(__file__).parent / 'fixtures/late_throw_call2.json').read_text())
        points = '{' + ','.join('{%s,{%s}}' % (t, ','.join(map(str, p)))
                                for t, p in data['positions']) + '}'
        replay('''
local points = ''' + points + '''
local start=FAKE_TIME
local index=0
local pos=sr.Unit.world_position
sr.Unit.world_position=function(unit)
    if unit==BEACON then return index==0 and {-5,25,24} or points[index][2] end
    return pos(unit)
end
ST.beacon_arc=1
tick(5)
index=1
tick(5)
start=FAKE_TIME
for i=2,#points do
    index=i
    FAKE_TIME=start+points[i][1]
    update()
end
M.tracks={incoming={trail={{-100,-100,180}},heading={0.6,0.8,-0.2},seen=FAKE_TIME+100}}
tick(10)
local found=false
for _,imp in pairs(M.impacts) do
    if math.abs(imp.p[1]-40.2189)<0.01 and math.abs(imp.p[2]-57.2111)<0.01 then
        found=imp.heading~=nil
    end
end
assert(found,'late throw permanently lost its ground and sky guide after the pause')
assert(M.flow_seg and #M.flow_seg>0,'recovered strike did not submit its directional glyphs')
''')

    def test_retired_unit_can_be_used_for_a_distinct_new_throw(self):
        replay(THROW + '''
ST.aircraft_up=false
tick(35)
assert(next(M.impacts)==nil,'fixture strike did not retire')
local pos=sr.Unit.world_position
local p={300,100,40}
sr.Unit.world_position=function(unit)
    if unit==BEACON then return p end
    return pos(unit)
end
tick(5)
p={330,120,12}
tick(5)
M.tracks={incoming={trail={{100,120,100}},heading={1,0,0},seen=FAKE_TIME+100}}
tick(25)
assert(next(M.impacts)~=nil,'reused moving unit retained a permanent retired flag')
''')

    def test_sky_and_ground_both_move_and_sky_is_one_low_upright_plane_per_glyph(self):
        replay(SCENE + '''
frames(45)
FAKE_TIME=200
frames(1)
local x,zmin,zmax={}, {}, {}
local count=0
for _,s in ipairs(M.flow_seg or {}) do
    if s[1]:match('^sky%d$') then
        local id=s[1]
        x[id]=x[id] or s[2][1]
        for k=2,3 do
            zmin[id]=math.min(zmin[id] or math.huge,s[k][3])
            zmax[id]=math.max(zmax[id] or -math.huge,s[k][3])
        end
        count=count+1
    end
end
assert(count>=150,'sky arrows must have filled interiors, not a few outline strokes')
assert(zmax.sky1<16,'sky arrows were not lowered')
for id,z in pairs(zmin) do
    assert(zmax[id]-z>6 and zmax[id]-z<6.5,'sky arrow must stand upright')
end
for _,s in ipairs(M.flow_seg) do
    if s[1]:match('^sky%d$') then
        for k=2,3 do assert(math.abs(s[k][2])<0.001,'sky glyph is still laid across the ground') end
    end
end
frames(10)
for _,s in ipairs(M.flow_seg or {}) do
    if x[s[1]] then
        assert(s[2][1]>x[s[1]]+2 and s[2][1]<x[s[1]]+4,'sky arrows did not travel forward')
        x[s[1]]=nil
    end
end
assert(next(x)==nil,'a sky glyph vanished during ordinary motion')
local marker=0
for _,s in ipairs(M.seg) do
    if s[1]=='marker' then
        marker=marker+1
        for k=2,3 do
            assert(math.abs(s[k][1])<=1.5 and math.abs(s[k][2])<=1.5,'landing cue is still oversized')
            assert(s[k][3]<=3.7,'landing cue is still too tall')
        end
    end
end
assert(marker>=35,'landing diamond has no filled interior')
''')

    def test_unbound_warning_recovers_after_a_longer_resource_query_gap(self):
        replay(THROW + '''
local imp=M.impacts[next(M.impacts)]
imp.aircraft=nil
M.tracks={}
ST.aircraft_up=false
ST.beacon_arc=0
tick(35)
assert(next(M.impacts)==nil,'unbound missing beacon should hide its stale position')
ST.beacon_arc=5
M.tracks={incoming={trail={{-100,0,100}},heading={1,0,0},seen=FAKE_TIME+100}}
tick(10)
assert(next(M.impacts)~=nil,'a resource query gap permanently retired a visible landed beacon')
''')

    def test_gap_recovery_does_not_extend_the_original_unbound_lifetime(self):
        replay(THROW + '''
local imp=M.impacts[next(M.impacts)]
local deadline=imp.born+20
imp.aircraft=nil
M.tracks={}
ST.aircraft_up=false
ST.beacon_arc=0
tick(35)
ST.beacon_arc=5
tick(10)
assert(next(M.impacts)~=nil,'fixture must recover an unbound warning')
assert(M.impacts[next(M.impacts)].born==imp.born,'recovery restarted the age deadline')
FAKE_TIME=deadline+1
tick(10)
assert(next(M.impacts)==nil,'unbound warning survived its original deadline')
tick(40)
assert(next(M.impacts)==nil,'expired stationary beacon resurrected repeatedly')
''')

    def test_fill_rows_cover_arrow_interiors_with_bounded_spacing(self):
        replay(SCENE + '''
frames(45)
local positions={}
for _,s in ipairs(M.flow_seg) do
    if (s[1]=='flow' or s[1]=='sky1') and math.abs(s[2][1]-s[3][1])<0.001 then
        assert(math.abs(s[2][2]+s[3][2])<0.001,'fill escaped the arrow silhouette')
        positions[s[1]]=positions[s[1]] or {}
        positions[s[1]][#positions[s[1]]+1]=s[2][1]
    end
end
for kind,values in pairs(positions) do
    table.sort(values)
    local spacing=kind=='flow' and 0.121 or 0.151
    local close=0
    for i=2,#values do
        if values[i]-values[i-1]<1 then
            assert(values[i]-values[i-1]<=spacing,'sparse stripes replaced a filled interior')
            close=close+1
        end
    end
    assert(close>=30,'arrow has only an outline')
end
assert(positions.flow and positions.sky1,'filled glyphs were not actually submitted')
''')


if __name__ == '__main__':
    unittest.main()
