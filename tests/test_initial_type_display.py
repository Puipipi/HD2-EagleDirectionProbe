"""The first visible reference footprint must not flash generic before type confirmation."""
import unittest
from test_mission_feedback import replay
from test_type_display import TYPES, FLAT
from test_solid_renderer import GUI


class InitialTypeDisplayTest(unittest.TestCase):
    def test_real_throw_identifies_during_settle_before_the_impact_is_created(self):
        replay(TYPES+'''
local p={500,100,40}
local original=sr.Unit.world_position
sr.Unit.world_position=function(unit) if unit==BEACON then return p end return original(unit) end
type_rows={{type=3,p={600,100,10}}}
ST.beacon_arc=5
tick(5)
p={600,100,10}
local landed=false
for i=1,30 do
    tick(1)
    for _,imp in pairs(M.impacts) do
        assert(imp.stratagem_type==3,'type recognition still starts after landing')
        landed=true
    end
end
assert(landed and type_reads<=8,'prefetch increased query cadence or blocked landing')
-- The game may reuse a beacon unit for the next throw. Its old confirmed type
-- must not survive a new high-speed throw / settling cycle.
type_rows={{type=18,p={700,100,10}}}
for _,imp in pairs(M.impacts) do imp.born=FAKE_TIME-120 end
tick(2) -- retire the old unbound guide before its beacon unit is reused
p={700,100,10}
tick(30)
local fresh=false
for id,imp in pairs(M.impacts) do
    if id>=2 then
        assert(imp.stratagem_type==18,'reused beacon inherited the previous throw type')
        fresh=true
    end
end
assert(fresh)
''')

    def test_prelanding_candidate_expires_across_a_long_beacon_query_gap(self):
        replay(TYPES+'''
local p={500,100,40}
local original=sr.Unit.world_position
sr.Unit.world_position=function(unit) if unit==BEACON then return p end return original(unit) end
type_rows={{type=3,p={600,100,10}}}
ST.beacon_arc=5;tick(5);p={600,100,10}
for i=1,20 do
    tick(1)
    if type_reads>=2 then break end
end
assert(type_reads>=2 and next(M.impacts)==nil,'fixture did not pause between type confirmation and landing')
ST.beacon_arc=0;tick(40)
p={603,100,10};type_rows={{type=18,p={603,100,10}}}
ST.beacon_arc=5
for i=1,20 do
    tick(1)
    for _,imp in pairs(M.impacts) do
        assert(imp.stratagem_type~=3,'stale provisional type was inherited after the query gap')
    end
end
local n=0
for _,imp in pairs(M.impacts) do assert(imp.stratagem_type==18);n=n+1 end
assert(n==1,'restored beacon did not complete fresh type confirmation')
''')

    def test_squad_settling_candidates_keep_independent_types_before_display(self):
        replay(TYPES+'''
local balls,positions={},{}
type_rows={}
for i=1,4 do
    balls[i]={};positions[balls[i]]={i*300,100,40}
    type_rows[i]={type=i%2==0 and 18 or 3,p={i*300+100,100,10}}
end
local query,position=sr.World.units_by_resource,sr.Unit.world_position
sr.World.units_by_resource=function(world,key)
    if key=='16f397ca5f51f271' then return balls end
    return query(world,key)
end
sr.Unit.world_position=function(unit) return positions[unit] or position(unit) end
tick(5)
for i,ball in ipairs(balls) do positions[ball]={i*300+100,100,10} end
local count=0
for j=1,30 do
    tick(1);count=0
    for _,imp in pairs(M.impacts) do
        for i,ball in ipairs(balls) do if imp.beacon==ball then
            assert(imp.stratagem_type==type_rows[i].type,'squad prefetch lost/mixed a ball type')
            count=count+1
        end end
    end
end
assert(count==4,'prefetch capped or delayed squad landing')
''')

    def test_known_type_never_draws_the_generic_footprint_before_confirmation(self):
        for type_id in (18,3):
            with self.subTest(type_id=type_id):
                replay(GUI+TYPES+FLAT+f'\ntype_rows[1].type={type_id}\n'+'''
local shown=false
for i=1,20 do
    frames(1)
    for _,s in ipairs(M.seg or {}) do if s[1]=='ground' then
        assert(M.impacts[1].stratagem_type,'default corridor flashed before type confirmation')
        shown=true
    end end
end
assert(shown,'confirmed footprint never appeared')
assert(max_frame<=2 and type_reads<=6,'initial display increased polling frequency')
''')

    def test_unavailable_type_reader_keeps_candidate_and_aircraft_cue_without_eagle_corridor(self):
        replay(TYPES+FLAT+'''
type_rows=nil
frames(20)
local n=0
for _,s in ipairs(M.seg or {}) do if s[1]=='ground' then n=n+1 end end
local air=0;for _,s in ipairs(M.seg or {}) do if s[1]=='air' then air=air+1 end end
assert(n==0 and M.impacts[1] and not M.impacts[1].stratagem_type,
    'unavailable type reader must retain the candidate without inventing an Eagle corridor')
assert(air>0,'unknown candidate hid the independent aircraft guide')
''')

    def test_ambiguous_and_empty_records_wait_then_keep_eagle_geometry_hidden(self):
        for records in ('{}','{{type=3,p={0,0,0}},{type=18,p={0,0,0}}}'):
            with self.subTest(records=records):
                replay(GUI+TYPES+FLAT+'\ntype_rows='+records+'''
frames(1)
assert(M.impacts[1].type_display_wait,'fresh lookup did not defer its unknown footprint')
local marker,sky,air=0,0,0
for _,batch in ipairs({M.seg,M.flow_seg}) do for _,s in ipairs(batch) do
    assert(s[1]~='ground' and s[1]~='flow' and not s[1]:match('^cordon'),
        'pending profile still showed generic range geometry')
    if s[1]=='marker' then marker=marker+1 end
    if s[1]=='sky1' then sky=sky+1 end
    if s[1]=='air' then air=air+1 end
end end
assert(marker==0 and sky==0 and air>0,
    'unconfirmed candidate must retain the aircraft arrow but hide Eagle impact cues')
frames(11)
assert(not M.impacts[1].type_display_wait and not M.impacts[1].stratagem_type)
frames(35)
local ground=0
for _,s in ipairs(M.seg) do if s[1]=='ground' then ground=ground+1 end end
assert(ground==0 and M.impacts[1] and not M.impacts[1].stratagem_type,
    'ambiguous/empty type result was treated as a confirmed Eagle corridor')
''')

    def test_range_disabled_does_not_bypass_positive_confirmation_gate(self):
        replay(TYPES+FLAT+'''
M.adapt_range=false
-- Use the existing beacon-height fallback so terrain cache warmup cannot mask
-- the profile display decision that this regression checks.
M.terrain_retry_at=FAKE_TIME+10;M.terrain_active=false
frames(1)
assert(not M.impacts[1].type_display_wait,'range-off mode acquired an unnecessary wait')
local ground=0
for _,s in ipairs(M.seg) do if s[1]=='ground' then ground=ground+1 end end
assert(ground==0 and M.impacts[1] and not M.impacts[1].stratagem_type,
    'range-off mode bypassed the positive Eagle confirmation gate')
''')


if __name__=='__main__': unittest.main()
