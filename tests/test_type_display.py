"""Actual guide drawing consumes conservative native type matches and saved controls."""
import unittest
from test_mission_feedback import replay
from test_terrain_query import SCENE
from test_departure_options_performance import MENU
from test_solid_renderer import GUI

TYPES='''
local type_reads=0
local type_rows={{type=18,p={0,0,0},anchor={0,100,0}}}
local type_epoch='mission-one'
package.preload['mods/codex/eagle_stratagem_profiles']=function()
    local p=os.getenv('DSH_PROBE_PATH'):gsub('eagle_direction_probe.lua$','stratagem_profiles.lua')
    return assert(loadfile(p))()
end
package.preload['mods/codex/eagle_stratagem_query']=function()
    return {new=function() return {snapshot=function()
        type_reads=type_reads+1
        return type_rows,type_rows and 'READY' or 'UNAVAILABLE: fixture',type_epoch
    end} end}
end
'''
FLAT=SCENE.replace("return math.max(0, 30 - math.abs(x - 60)), 'HIT'","return 0, 'HIT'")


class TypeDisplayTest(unittest.TestCase):
    def test_typed_airstrike_changes_only_reference_bounds_and_moving_label(self):
        replay(TYPES+FLAT+'''
frames(50)
local imp=M.impacts[1]
assert(imp.stratagem_type==18,'native type did not reach the actual strike')
assert(imp.heading[1]==1 and imp.heading[2]==0,'anchor changed the aircraft approach')
assert(M.type_labels[1]=='REF AIRSTRIKE','specific moving label missing')
local lo,hi,side=math.huge,-math.huge,0
for _,s in ipairs(M.seg) do
    if s[1]=='ground' then
        for k=2,3 do
            lo,hi=math.min(lo,s[k][1]),math.max(hi,s[k][1])
            side=math.max(side,math.abs(s[k][2]))
        end
    end
end
assert(math.abs(lo+60)<0.01 and math.abs(hi-60)<0.01 and math.abs(side-10.25)<0.01,
    'airstrike reference footprint did not adapt')
assert(max_frame<=2 and casts<=85,'type adaptation exceeded shared terrain budget')
local before,oldcasts=type_reads,casts
frames(10)
assert(type_reads-before<=3 and casts==oldcasts,'type reads or height cache ran per frame')
''')

    def test_500kg_uses_circular_reference_and_true_faces_follow_wide_cached_grid(self):
        replay(GUI+TYPES+FLAT+'''
type_rows[1].type=3
frames(60)
assert(M.impacts[1].stratagem_type==3 and M.type_labels[1]=='REF 500KG')
assert(M.solid_active and creates>0)
local n=0
for _,s in ipairs(M.seg) do
    if s[1]=='ground' then
        n=n+1
        for k=2,3 do
            local p=s[k];local r=math.sqrt(p[1]^2+p[2]^2)
            assert(r>=24.74 and r<=25.26,'500kg boundary is not circular')
        end
    end
end
assert(n>=96 and max_frame<=2,'circle missing or extra terrain calls introduced')
M.tracks={};M.track_order={};M.impacts={};frames(1)
assert(next(faces)==nil,'type-specific guide survived strike retirement')
''')

    def test_napalm_calibrated_ends_hold_ground_sky_and_six_flow_cycles(self):
        replay(GUI+TYPES+FLAT+MENU+'''
type_rows[1].type=133
frames(60)
local imp=M.impacts[1]
assert(imp.stratagem_type==133 and M.type_labels[1]=='REF NAPALM')
local center={unpack(imp.p)};local heading={unpack(imp.heading)}
local bound=100/3
local function along(x,y)
    return (x-center[1])*heading[1]+(y-center[2])*heading[2]
end
local lo,hi,lateral,ground=math.huge,-math.huge,0,0
for _,s in ipairs(M.seg) do if s[1]=='ground' or s[1]=='area' then
    for k=2,#s do if type(s[k])=='table' then
        local p=s[k];local t=along(p[1],p[2])
        lo,hi=math.min(lo,t),math.max(hi,t)
        local side=-(p[1]-center[1])*heading[2]+(p[2]-center[2])*heading[1]
        lateral=math.max(lateral,math.abs(side))
        if s[1]=='ground' then ground=ground+1 end
        assert(t>=-bound-0.001 and t<=bound+0.001,
            'Napalm ground endpoint exceeded the user-calibrated range')
    end end
end end
assert(ground>0 and math.abs(lo+bound)<0.01 and math.abs(hi-bound)<0.01,
    'Napalm ground ends did not use the calibrated span')
assert(math.abs(lateral-10.25)<0.01,'Napalm width or center moved with the length calibration')

-- Six complete flow wraps exercise moving light triangles, plus their edge phases.
for i=0,360 do
    FAKE_TIME=210+i*0.05;update()
    local flow,sky=0,0
    for _,s in ipairs(M.flow_seg) do
        if s[1]=='flow' or s[1]:match('^sky%d$') then
            if s[1]=='flow' then flow=flow+1 else sky=sky+1 end
            for k=2,#s do if type(s[k])=='table' then
                local t=along(s[k][1],s[k][2])
                assert(t>=-bound-0.001 and t<=bound+0.001,
                    'moving Napalm ground/sky geometry left the calibrated range')
            end end
        end
    end
    assert(flow>0 and sky>0,'Napalm moving ground/sky reference disappeared during a cycle')
end
assert(imp.p[1]==center[1] and imp.p[2]==center[2] and imp.p[3]==center[3]
    and imp.heading[1]==heading[1] and imp.heading[2]==heading[2],
    'Napalm length calibration moved its center or incoming heading')
assert(M.type_profiles.bounds(18).lo==-60 and M.type_profiles.bounds(18).hi==60,
    'Napalm calibration changed Airstrike bounds')
apply('adapt_range',false);frames(45)
local generic=0
for _,s in ipairs(M.seg) do if s[1]=='ground' then
    for k=2,3 do generic=math.max(generic,math.abs(along(s[k][1],s[k][2]))) end
end end
assert(generic>=99.9,'range-off failed to restore the generic guide')
''')

    def test_controls_restore_and_independently_disable_names_and_ranges(self):
        replay(TYPES+FLAT+MENU+'''
saved['eagle_direction_probe.adapt_range']=false
frames(50)
assert(rows['eagle_direction_probe.show_type'].default and not M.adapt_range)
assert(M.type_labels[1]=='REF AIRSTRIKE')
local function far()
    local hi=0
    for _,s in ipairs(M.seg) do if s[1]=='ground' then hi=math.max(hi,s[2][1],s[3][1]) end end
    return hi
end
assert(far()==100,'saved range-off value ignored')
apply('adapt_range',true);frames(45)
assert(math.abs(far()-60)<0.01)
apply('show_type',false);frames(1)
assert(M.type_labels[1]=='EAGLE ?' and math.abs(far()-60)<0.01)
apply('adapt_range',false);frames(45)
local n=type_reads;frames(20)
assert(type_reads==n and far()==100,'disabled type/range options kept querying')
''')

    def test_failed_or_ambiguous_snapshot_keeps_original_generic_guide(self):
        for suffix in ("type_rows=nil", "type_rows[2]={type=65,p={0.1,0,0}}",
                       "type_rows[2]={type=999,p={0.1,0,0}}"):
            with self.subTest(suffix=suffix):
                replay(TYPES+FLAT+suffix+'''
frames(50)
assert(not M.impacts[1].stratagem_type and M.type_labels[1]=='EAGLE ?')
local far=0
for _,s in ipairs(M.seg) do if s[1]=='ground' then far=math.max(far,s[2][1],s[3][1]) end end
assert(far==100 and FRAME_HAS_LINES,'unknown type removed or changed the generic guide')
assert(max_frame<=2)
''')

    def test_short_forward_strafe_always_has_a_readable_moving_label_pair(self):
        replay(TYPES+FLAT+'''
type_rows[1].type=30
frames(60)
assert(M.type_labels[1]=='REF STRAFE')
local h=M.impacts[1].heading
for i=0,59 do
    FAKE_TIME=210+i*0.05;update()
    local letters=0
    for _,s in ipairs(M.flow_seg) do
        if s[1]=='cordon_text' then letters=letters+1 end
        if s[1]=='cordon' or s[1]=='cordon_dim' then
            for k=2,(s[4] and 4 or 3) do
                assert(s[k][1]>=-5.01 and s[k][1]<=55.01,'panel left forward footprint')
            end
        end
    end
    assert(letters>0,'short strip lost its moving label during wrap')
end
assert(M.impacts[1].heading==h,'typing changed departure axis state')
''')

    def test_short_footprints_keep_ground_arrows_visible_through_the_motion_cycle(self):
        for type_id in (3,30):
            with self.subTest(type_id=type_id):
                replay(TYPES+FLAT+f'type_rows[1].type={type_id}\n'+'''
frames(60)
for i=0,60 do
    FAKE_TIME=210+i*0.05;update()
    local n=0
    for _,s in ipairs(M.flow_seg) do if s[1]=='flow' then n=n+1 end end
    assert(n>0,'short reference footprint lost every moving ground arrow')
end
''')


if __name__=='__main__': unittest.main()
