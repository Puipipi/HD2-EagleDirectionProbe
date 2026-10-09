"""Mission feedback: depth menu, compact cues, cached directional movement."""
import unittest

from test_mission_feedback import replay, THROW
from test_terrain_query import SCENE


MENU = '''
local saved=true
local registered,changed
local rows,callbacks={},{}
local host={api=1}
host.register_option=function(id,spec)
    assert(spec.type=='toggle','display controls must be toggles')
    if id=='eagle_direction_probe.through_world' then
        assert(spec.default==false,'see-through must default off')
        registered=id
    end
    rows[id]=spec
    return true
end
host.get=function(id)
    if id==registered then return saved end
    return rows[id].default
end
host.on_change=function(id,callback)
    if id==registered then changed=callback end
    callbacks[id]=callback
    return true
end
_G.ModOptionsMenu=host
'''


class DisplayFeedbackTest(unittest.TestCase):
    def test_five_sky_arrows_stay_at_the_beacon_when_the_aircraft_moves(self):
        replay(SCENE + '''
frames(45)
local function sky_signature()
    local kinds,points={},{}
    for _,s in ipairs(M.flow_seg or {}) do
        if s[1]:match('^sky%d$') then
            kinds[s[1]]=true
            for k=2,3 do
                assert(s[k][3]>=8.5 and s[k][3]<50,'sky guide is not above the sampled ground')
                points[#points+1]=string.format('%.3f,%.3f,%.3f',unpack(s[k]))
            end
        end
    end
    assert(kinds.sky1 and kinds.sky2 and kinds.sky3 and kinds.sky4 and kinds.sky5,
        'five separate sky arrows are required')
    return table.concat(points,'|')
end
local before=sky_signature()
M.tracks.design.trail={{500,400,80}}
M.geom_key=nil
FAKE_TIME=FAKE_TIME-0.05 -- compare the same conveyor phase with a different aircraft position
frames(1)
assert(sky_signature()==before,'sky arrows followed the aircraft instead of the landing point')
M.impacts[1].heading={0,1,0}
M.tracks.design.heading={0,1,0}
M.geom_key=nil
frames(1)
for _,s in ipairs(M.flow_seg) do
    if s[1]:match('^sky%d$') then
        for k=2,3 do assert(math.abs(s[k][1])<=4,'sky arrow ignored changed incoming heading') end
    end
end
''')

    def test_menu_can_hide_ground_and_sky_independently(self):
        replay(SCENE + MENU + '''
frames(45)
local sky_id='eagle_direction_probe.show_sky'
local ground_id='eagle_direction_probe.show_ground_border'
local triangles_id='eagle_direction_probe.show_ground_triangles'
assert(callbacks[sky_id] and callbacks[ground_id] and callbacks[triangles_id],
    'independent display toggles are missing')
callbacks[ground_id](false)
callbacks[triangles_id](false)
frames(1)
local sky=false
for _,s in ipairs(M.seg) do
    assert(s[1]~='ground' and s[1]~='marker','ground outline remained after hiding ground')
end
for _,s in ipairs(M.flow_seg or {}) do
    assert(s[1]~='flow','ground animation remained after disabling ground')
    if s[1]:match('^sky%d$') then sky=true end
end
assert(sky,'hiding ground also removed sky')
callbacks[sky_id](false)
frames(1)
local stopped=casts
frames(20)
assert(casts==stopped,'hidden ground and sky continued collision sampling')
for _,batch in ipairs({M.seg,M.flow_seg or {}}) do
    for _,s in ipairs(batch) do assert(not s[1]:match('^sky'),'sky arrows remained after disabling') end
end
callbacks[ground_id](true)
callbacks[triangles_id](true)
frames(1)
assert(#(M.flow_seg or {})>0,'ground animation did not return after reenabling')
''')

    def test_sky_has_only_arrows_and_lifts_each_arrow_above_distant_cached_ground(self):
        replay(SCENE + '''
frames(45)
local raised=false
for _,s in ipairs(M.flow_seg) do
    if s[1]=='sky5' then
        for k=2,3 do
            if s[k][3]>30 then raised=true end
        end
    elseif s[1]=='sky_edge' then
        for k=2,3 do
            assert(math.abs(s[k][2])<0.01,'sky boundary remained after requesting arrows only')
        end
    end
end
assert(raised,'sky arrows stayed flat over the distant ridge')
''')

    def test_refused_menu_does_not_disable_guides_and_successful_rows_are_not_duplicated(self):
        replay(SCENE + MENU + '''
local register=host.register_option
local fail=true
local subscriptions={}
host.register_option=function(id,spec)
    if id=='eagle_direction_probe.show_ground_border' and fail then error('menu temporarily refuses row') end
    return register(id,spec)
end
local subscribe=host.on_change
host.on_change=function(id,callback)
    subscriptions[id]=(subscriptions[id] or 0)+1
    return subscribe(id,callback)
end
frames(45)
assert(FRAME_HAS_LINES and not M.draw_off,'menu failure disabled rendering')
fail=false
frames(25)
assert(callbacks['eagle_direction_probe.show_ground_border'],'refused row was never retried')
for _,n in pairs(subscriptions) do assert(n==1,'retry duplicated a successful callback') end
''')

    def test_default_lines_obey_depth_even_without_an_options_menu(self):
        replay(THROW + '''
assert(M.line.flag==false,'default warnings still show through buildings')
assert(FRAME_HAS_LINES,'depth testing must not disable the guides')
''')

    def test_late_menu_restores_saved_choice_and_changes_live_line_depth(self):
        replay(THROW + MENU + '''
tick(25)
assert(registered and changed,'late-loaded Mod Options Menu was not registered')
assert(M.line.flag==true,'saved enabled choice was not applied')
local before=M.line
local strike=next(M.impacts)
changed(false,registered)
tick(1)
assert(M.line.flag==false and M.line~=before,'live line retained the old depth flag')
assert(M.impacts[strike] and FRAME_HAS_LINES,'changing depth reset a live strike')
before=M.line
changed(true,registered)
tick(1)
assert(M.line.flag==true and M.line~=before,'enabling see-through did not recreate the line')
assert(M.impacts[strike] and FRAME_HAS_LINES,'reenabling lost the warning')
''')

    def test_animation_moves_forward_without_requerying_or_rebuilding_static_geometry(self):
        replay(SCENE + '''
frames(45)
FAKE_TIME=200
frames(1)
assert(M.flow_seg and #M.flow_seg>=20,'small moving ground arrows are missing')
local static,old_casts=M.seg,casts
local x=M.flow_seg[1][2][1]
frames(10)
assert(M.flow_seg[1][2][1]>x+2 and M.flow_seg[1][2][1]<x+4,
    'ground arrows must advance along the incoming heading')
assert(M.seg==static,'animation rebuilt the complete static geometry')
assert(casts==old_casts,'animation caused new terrain queries')
local raised=false
for _,s in ipairs(M.flow_seg) do
    for k=2,3 do
        if s[k][1]>50 and s[k][1]<70 and s[k][3]>15 then raised=true end
    end
end
assert(raised,'animated arrows ignored cached distant terrain')
''')

    def test_140_fps_keeps_motion_updates_bounded_and_clears_them_on_retirement(self):
        replay(SCENE + '''
frames(45)
FAKE_TIME=200
local prior,rebuilds=nil,0
local old_casts=casts
for i=1,140 do
    FAKE_TIME=FAKE_TIME+1/140
    update()
    if M.flow_seg~=prior then rebuilds=rebuilds+1; prior=M.flow_seg end
    assert(FRAME_HAS_LINES,'animation caused a blank frame')
end
assert(rebuilds>5 and rebuilds<=22,'motion should update about 20 times, not 140 times')
assert(casts==old_casts,'animation restarted the collision grid')
M.tracks,M.track_order,M.impacts={},{},{}
frames(1)
assert(not FRAME_HAS_LINES and #(M.flow_seg or {})==0,'moving arrows outlived the strike')
''')

    def test_ground_symbols_are_compact_and_still_have_upright_landing_cues(self):
        replay(SCENE + '''
frames(45)
local ymax,top=0,0
for _,s in ipairs(M.seg or {}) do
    if s[1]=='ground' or s[1]=='holo' and math.max(s[2][3],s[3][3])<60 then
        for k=2,3 do ymax=math.max(ymax,math.abs(s[k][2])) end
    elseif s[1]=='marker' then
        for k=2,3 do
            assert(math.abs(s[k][1])<=4.5 and math.abs(s[k][2])<=4.5,
                'oversized landing marker dominates nearby ground')
            top=math.max(top,s[k][3])
        end
    end
end
assert(ymax<=6.5,'ground strip is still too wide')
assert(top>=3.5 and top<=3.7,'landing cue must retain a small upright shape')
''')


if __name__=='__main__':
    unittest.main()
