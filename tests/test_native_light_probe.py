"""Native light prototype owns its helpers, checks resources and cleans them up."""
import unittest
from test_mission_feedback import replay
from test_type_display import FLAT
from test_departure_options_performance import MENU


NATIVE = '''
local owned,spawned,removed,moved={},0,0,0
local available=true
local failures=false
local original_alive=sr.Unit.alive
sr.Application.can_get=function(kind,name)
    assert(kind=='unit' and name=='content/helmet_headlamp/runtime_mode_profiles')
    return available
end
sr.World.spawn_unit=function(world,name,...)
    assert(world==WORLD and available and select('#',...)==0)
    assert(name=='content/helmet_headlamp/runtime_mode_profiles')
    spawned=spawned+1
    local u={id=spawned,alive=true,lights={}}
    for i=0,4 do u.lights[i]={owner=u,enabled=true} end
    owned[u]=true
    return u
end
sr.World.destroy_unit=function(world,u)
    assert(world==WORLD and owned[u] and u.alive,'destroyed another mod or stale unit')
    for _,l in pairs(u.lights) do assert(not l.enabled,'helper destroyed while still lit') end
    u.alive=false;removed=removed+1
end
sr.Unit.alive=function(u)
    if owned[u] then return u.alive end
    return original_alive(u)
end
sr.Unit.node=function(u,name) assert(owned[u] and name=='StingrayEntityRoot');return 0 end
sr.Unit.num_lights=function(u) assert(owned[u]);return 5 end
sr.Unit.has_light=function(u,name) assert(owned[u]);return name=='helmet_headlamp_task_fill' end
sr.Unit.light=function(u,which)
    assert(owned[u] and u.alive,'touched player headlamp or stale helper')
    return u.lights[which=='helmet_headlamp_task_fill' and 0 or which]
end
sr.Unit.set_local_position=function(u,node,v)
    assert(owned[u] and node==0 and v[1]==v[1] and v[3]>0)
    u.p={v[1],v[2],v[3]};moved=moved+1
end
sr.Unit.set_local_rotation=function(u,node,q)
    assert(owned[u] and node==0 and q.x==1 and q.y==0 and q.z==0
        and math.abs(q.angle+math.pi/2)<0.0001,'spotlight does not point down')
end
sr.Unit.set_unit_visibility=function(u,v) assert(owned[u] and v==false);u.hidden=true end
sr.World.update_unit=function(world,u) assert(world==WORLD and owned[u]) end
sr.Quaternion={axis_angle=function(v,a) return {x=v[1],y=v[2],z=v[3],angle=a} end}
sr.Light={
    set_enabled=function(l,v) assert(owned[l.owner]);l.enabled=v end,
    set_color=function(l,v)
        assert(owned[l.owner]);if failures then error('configuration fixture') end
        l.rgb={v[1],v[2],v[3]}
    end,
    set_spot_angle_start=function(l,v) assert(owned[l.owner]);l.inner=v end,
    set_spot_angle_end=function(l,v) assert(owned[l.owner]);l.outer=v end,
    set_falloff_end=function(l,v) assert(owned[l.owner]);l.reach=v end,
    set_casts_shadows=function(l,v) assert(owned[l.owner] and not v) end,
    set_volumetric_enabled=function(l,v) assert(owned[l.owner] and not v) end,
}
package.preload['mods/codex/eagle_native_light_probe']=function()
    local p=os.getenv('DSH_PROBE_PATH'):gsub('eagle_direction_probe.lua$','native_light_probe.lua')
    return assert(loadfile(p))()
end
local function live_count()
    local n=0;for u in pairs(owned) do if u.alive then n=n+1 end end;return n
end
'''


class NativeLightProbeTest(unittest.TestCase):
    def test_saved_toggle_creates_real_light_only_in_own_helper_without_red_face_overlay(self):
        replay(FLAT+MENU+NATIVE+'''
frames(50)
assert(spawned==0,'prototype created lights by default')
local queries=casts
apply('show_native_light_probe',true);frames(1)
assert(spawned==1 and live_count()==1,'native light prototype did not create a helper')
local u=next(owned)
assert(u.hidden and u.p[1]==0 and u.p[2]==0 and u.p[3]==12,'emitter not above actual beacon')
local lit=0
for _,l in pairs(u.lights) do if l.enabled then
    lit=lit+1
    assert(l.rgb[1]>1000 and l.rgb[2]<l.rgb[1]/20 and l.rgb[3]<l.rgb[1]/20,
        'prototype did not set native HDR red light colour')
    assert(l.outer>l.inner and l.reach>=20,'native cone/falloff not configured')
end end
assert(lit==1,'unused headlamp lights were left enabled')
apply('show_ground_area',true);frames(1)
for _,s in ipairs(M.seg) do assert(s[1]~='area','red face overlay obscures real-light experiment') end
local positions=moved;frames(20)
assert(spawned==1 and moved==positions and casts==queries,'static emitter updated or recast each frame')
apply('show_native_light_probe',false);frames(1)
assert(live_count()==0 and removed==1,'MOM off did not retire helper immediately')
''')

    def test_missing_resource_or_api_never_spawns_and_preserves_other_guides(self):
        for missing in ('available=false', 'sr.Light.set_color=nil'):
            with self.subTest(missing=missing):
                replay(FLAT+MENU+NATIVE+missing+'''
saved['eagle_direction_probe.show_native_light_probe']=true
frames(60)
assert(spawned==0 and #M.seg>0,'missing native light support broke existing drawing')
assert(M.native_light_status:find('unavailable',1,true),'unavailable reason missing')
''')

    def test_helper_repositions_without_respawn_and_retires_with_guide(self):
        replay(FLAT+MENU+NATIVE+'''
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(live_count()==1)
M.impacts[1].p={5,6,7};frames(1)
local u=next(owned)
assert(spawned==1 and u.p[1]==5 and u.p[2]==6 and u.p[3]==19,'emitter ignored changed beacon')
M.tracks={};M.track_order={};M.impacts={};frames(1)
assert(live_count()==0 and removed==1,'native red light outlived guide')
''')

    def test_many_guides_create_at_most_one_helper_per_frame_without_a_count_cap(self):
        replay(FLAT+MENU+NATIVE+'''
frames(50)
for i=2,8 do
    M.impacts[i]={p={i*10,0,0},heading={1,0,0},aircraft='design',beacon=BEACON,
        last_seen=FAKE_TIME+1000,t=FAKE_TIME}
end
apply('show_native_light_probe',true)
for i=1,10 do local n=spawned;frames(1);assert(spawned-n<=1,'light creation burst exceeded budget') end
assert(live_count()==8,'native light guide count capped')
apply('show_native_light_probe',false);frames(1)
assert(live_count()==0,'some teammate lights survived disable')
''')

    def test_partial_setup_failure_cleans_unit_and_throttles_retries(self):
        replay(FLAT+MENU+NATIVE+'''
failures=true
saved['eagle_direction_probe.show_native_light_probe']=true
frames(60)
assert(spawned>0 and spawned<=4 and removed==spawned and live_count()==0,
    'failed setup leaked a helper or retried every frame')
assert(#M.seg>0,'light failure disabled existing guide')
''')

    def test_scene_disappearance_never_destroys_through_a_dead_world(self):
        replay(FLAT+MENU+NATIVE+'''
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(live_count()==1)
local old=sr.Application.worlds
sr.Application.worlds=function() return {} end
frames(1)
assert(removed==0,'cleanup used a dead world handle')
sr.Application.worlds=old
-- Engine teardown owns the old world; emulate its destruction of old helpers.
for u in pairs(owned) do u.alive=false end
frames(2)
assert(live_count()==1,'new scene did not recover native prototype')
''')

    def test_resource_recovery_and_shutdown_work_without_gui_support(self):
        replay(FLAT+MENU+NATIVE+'''
available=false
saved['eagle_direction_probe.show_native_light_probe']=true
sr.World.create_world_gui=nil
frames(50)
assert(spawned==0)
available=true;frames(30)
assert(live_count()==1,'resource availability did not recover independently of GUI')
shutdown()
assert(live_count()==0 and removed==1,'shutdown left a light behind')
''')

    def test_drawing_failure_releases_light_even_after_render_loop_stops(self):
        replay(FLAT+MENU+NATIVE+'''
saved['eagle_direction_probe.show_native_light_probe']=true;frames(50)
assert(live_count()==1)
sr.LineObject.add_line=function() error('native line fixture failed') end
frames(1)
assert(M.draw_off,'fixture did not disable rendering')
apply('show_native_light_probe',false);frames(2)
assert(live_count()==0 and removed==1,'render failure bypassed native light cleanup')
assert(M.errors==1,'fixture did not report the line failure');M.errors=0
''')


if __name__ == '__main__': unittest.main()
