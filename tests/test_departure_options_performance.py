"""Departure stability, independent saved controls and repeated render work."""
import unittest

from test_mission_feedback import replay
from test_second_feedback import FLIGHT
from test_terrain_query import SCENE


MENU = '''
local rows,callbacks,values,saved,writes={},{},{},{},{}
local host={api=1}
host.register_option=function(id,spec)
    rows[id]=spec
    if values[id]==nil then
        values[id]=saved[id]
        if values[id]==nil then values[id]=spec.default end
    end
    return true
end
host.get=function(id) return values[id] end
host.set=function(id,v)
    assert(rows[id] and type(v)==type(rows[id].default),'invalid value or set before register/get')
    writes[#writes+1]={id,v}
    values[id],saved[id]=v,v
    return true
end
host.on_change=function(id,fn) callbacks[id]=fn; return true end
_G.ModOptionsMenu=host
local function apply(key,v)
    local id='eagle_direction_probe.'..key
    assert(callbacks[id],'missing control: '..key)
    values[id],saved[id]=v,v -- actual MOM applies/saves before notifying
    callbacks[id](v,id)
end
local function count(kind)
    local n=0
    for _,batch in ipairs({M.seg or {},M.flow_seg or {}}) do
        for _,s in ipairs(batch) do if s[1]==kind then n=n+1 end end
    end
    return n
end
'''


class DepartureOptionsPerformanceTest(unittest.TestCase):
    def test_captured_pullout_turn_keeps_attack_axis_before_the_nose_points_up(self):
        flight=FLIGHT.replace('return old_pos(unit)',
            "if unit==BEACON and ST.beacon_arc>=4 then return {18.2,-4.7,14.6} end\n    return old_pos(unit)")
        flight=flight.replace('p = {-100, 0, 100}', 'p = {200, 250, 200}')
        replay(flight + '''
local imp=M.impacts[next(M.impacts)]
assert(imp.p[1]==18.2 and imp.p[2]==-4.7 and not imp.attack_axis_locked)
-- Rounded position/forward samples from the reported rc1 mission, call 7.
-- Yaw begins while the nose still points down, before attack_climbing becomes true.
p,f={77.9,100,102.3},{-0.446,-0.782,-0.435};tick(4)
assert(not imp.attack_axis_locked,'axis locked before the actual 120m arrival gate')
p,f={49,46.5,83.2},{-0.452,-0.824,-0.340};tick(4)
assert(imp.attack_axis_locked,'axis did not lock on the captured low arrival')
local h={unpack(imp.heading)}
assert(math.abs(h[1]*f[2]-h[2]*f[1])<0.00001,'latched an earlier approach heading')
local curve={
    {{23.9,-7.3,79.4},{-0.437,-0.885,-0.162}},
    {{1.2,-64.8,89.6},{-0.392,-0.918,0.057}},
    {{-16.5,-119.8,112.2},{-0.324,-0.908,0.265}},
}
for _,row in ipairs(curve) do
    p,f=row[1],row[2];tick(4)
    assert(M.impacts[next(M.impacts)]==imp,'pullout freeze retired the guide early')
    assert(imp.heading[1]==h[1] and imp.heading[2]==h[2],
        'ground/sky attack axis followed the pullout yaw before nose-up detection')
end
assert(M.tracks[AIRCRAFT].heading[2]~=h[2],'aircraft arrow stopped following its live nose')
p,f={-28.5,-167.4,142.1},{-0.253,-0.867,0.430};tick(20)
assert(next(M.impacts)==nil and not FRAME_HAS_LINES,'locked attack guide failed to retire')
''')

    def test_shallow_departure_bank_does_not_rotate_ground_or_sky(self):
        replay(FLIGHT + '''
local imp=M.impacts[next(M.impacts)]
local h={unpack(imp.heading)}
p,f={-50,0,108},{0.8,0.55,0.15}
tick(2)
assert(imp.heading[1]==h[1] and imp.heading[2]==h[2],
    'ground and sky followed the shallow departure bank')
assert(M.tracks[AIRCRAFT].heading[2]>0.5,'aircraft arrow must keep its live heading')
assert(next(M.impacts) and FRAME_HAS_LINES,'a shallow climb prematurely retired the strike')
p,f={-20,20,111},{0.8,-0.6,0}
tick(2)
assert(imp.heading[1]==h[1] and imp.heading[2]==h[2],
    'a level bank above the attack low point resumed departure steering')
p,f={100,30,150},{0.6,-0.5,0.6}
tick(20)
assert(next(M.impacts)==nil and not FRAME_HAS_LINES,'locked warning did not retire')
''')

    def test_climb_freeze_recovers_on_a_return_to_the_attack_run(self):
        replay(FLIGHT + '''
p,f={-80,0,105},{0.8,0.55,0.15}
tick(2)
p,f={-40,0,100},{0,1,0}
tick(5)
local imp=M.impacts[next(M.impacts)]
assert(imp and imp.heading[2]>0.9,'temporary upward tilt permanently froze approach steering')
''')

    def test_four_default_on_controls_are_independent_and_sky_only_draws(self):
        replay(SCENE + MENU + '''
frames(45)
for _,key in ipairs({'show_air','show_sky','show_ground_border','show_ground_triangles'}) do
    local row=rows['eagle_direction_probe.'..key]
    assert(row and row.default==true,'requested default-on toggle missing: '..key)
end
apply('show_ground_border',false); frames(1)
assert(count('ground')==0 and count('holo')==0 and count('flow')>0 and count('marker')>0,
    'border switch also hid triangles/landing point')
apply('show_air',false); frames(1)
assert(count('air')==0 and count('trail')==0 and count('sky1')>0,'air switch affected sky')
apply('show_ground_triangles',false); frames(1)
assert(count('flow')==0 and count('marker')==0 and count('sky1')>0 and FRAME_HAS_LINES,
    'sky-only mode stopped drawing')
apply('show_sky',false); frames(1)
assert(not FRAME_HAS_LINES,'disabled graphics remained visible')
local before=casts; frames(20)
assert(casts==before,'all-hidden state kept collision work')
apply('show_ground_border',true); frames(1)
assert(count('ground')>0 and count('flow')==0 and count('sky1')==0 and FRAME_HAS_LINES,
    'border-only mode did not recover independently')
''')

    def test_saved_false_values_are_read_before_push_and_survive_a_new_menu_host(self):
        replay(SCENE + MENU + '''
saved['eagle_direction_probe.show_air']=false
saved['eagle_direction_probe.show_ground_border']=false
saved['eagle_direction_probe.show_sky']=false
frames(45)
assert(M.show_air==false and M.show_ground_border==false and M.show_sky==false,
    'saved false was replaced by a default')
assert(#writes==12,'effective choices were not synchronized to MOM like Cooldown')
for _,w in ipairs(writes) do
    assert(w[2]==values[w[1]],'a default overwrote a saved value during registration')
end
apply('show_ground_triangles',false); frames(1)
-- Simulate redeployment: new runtime defaults, new MOM state loaded from its saved store.
M.show_air,M.show_sky,M.show_ground_border,M.show_ground_triangles=true,true,true,true
values,rows,callbacks,writes={},{},{},{}
_G.ModOptionsMenu={api=1,register_option=host.register_option,get=host.get,
    set=host.set,on_change=host.on_change}
frames(25)
assert(not M.show_air and not M.show_sky and not M.show_ground_border and not M.show_ground_triangles,
    'redeployment lost modified choices')
assert(not FRAME_HAS_LINES,'restored all-hidden setting still drew warnings')
local n=#writes; frames(25)
assert(#writes==n,'settings were repeatedly written on a timer')
''')

    def test_aircraft_motion_reuses_completed_ground_geometry(self):
        replay(SCENE + '''
frames(45)
local function first_ground()
    for _,s in ipairs(M.seg) do if s[1]=='ground' then return s end end
end
local before=first_ground()
assert(before,'fixture must have completed terrain borders')
M.tracks.design.trail={{10,0,80}}
frames(2)
assert(first_ground()==before,'aircraft movement rebuilt unchanged ground geometry')
local air=false
for _,s in ipairs(M.seg) do if s[1]=='air' and s[2][1]>100 then air=true end end
assert(air,'ground cache also froze the live aircraft indicator')
''')


if __name__=='__main__':
    unittest.main()
