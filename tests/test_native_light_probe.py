"""Native light prototype owns its helpers, checks resources and cleans them up."""
import unittest
from test_mission_feedback import replay
from test_type_display import FLAT
from test_departure_options_performance import MENU


NATIVE = '''
local owned,spawned,removed,moved={},0,0,0
local setter_calls={enabled_true=0,color=0,intensity=0}
local available=true
local failures=false
local enabled_failure=false
local setup_failure=false
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
    for i=0,4 do u.lights[i]={owner=u,enabled=true,inner=1.92,outer=2.79,
        reach=30,shadows=true,volumetric=true,rgb={9000,8550,7560},intensity=1} end
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
local getter_calls={color=0,intensity=0}
local light_index={
    helmet_headlamp_task_fill=0,helmet_headlamp_task_soft_reach=1,
    helmet_headlamp_gameplay_fill=2,helmet_headlamp_gameplay_direction=3,
    helmet_headlamp_default_task=4,
}
sr.Unit.has_light=function(u,name) assert(owned[u]);return light_index[name]~=nil end
sr.Unit.light=function(u,which)
    assert(owned[u] and u.alive,'touched player headlamp or stale helper')
    local index=type(which)=='string' and light_index[which] or which
    assert(index~=nil,'unknown named light')
    return u.lights[index]
end
sr.Unit.set_local_position=function(u,node,v)
    assert(owned[u] and node==0 and v[1]==v[1] and v[3]>0)
    u.p={v[1],v[2],v[3]};moved=moved+1
end
sr.Unit.set_local_rotation=function(u,node,q)
    assert(owned[u] and node==0 and q.x==1 and q.y==0 and q.z==0
        and math.abs(q.angle+math.pi/2)<0.0001,'spotlight does not point down')
end
sr.Unit.set_unit_visibility=function(u,v)
    assert(owned[u] and v==false)
    if setup_failure then error('setup fixture') end
    u.hidden=true
end
sr.World.update_unit=function(world,u) assert(world==WORLD and owned[u]) end
sr.Quaternion={axis_angle=function(v,a) return {x=v[1],y=v[2],z=v[3],angle=a} end}
sr.Light={
    set_enabled=function(l,v)
        assert(owned[l.owner]);if v then
            setter_calls.enabled_true=setter_calls.enabled_true+1
            if enabled_failure then error('keepalive fixture') end
        end
        l.enabled=v
    end,
    set_color=function(l,v)
        setter_calls.color=setter_calls.color+1
        assert(owned[l.owner]);if failures then error('configuration fixture') end
        l.rgb={v[1],v[2],v[3]}
    end,
    set_intensity=function(l,v)
        setter_calls.intensity=setter_calls.intensity+1
        assert(owned[l.owner]);if failures then error('configuration fixture') end
        l.intensity=v
    end,
    color=function(l)
        assert(owned[l.owner],'read a light not owned by the probe')
        getter_calls.color=getter_calls.color+1
        return {l.rgb[1],l.rgb[2],l.rgb[3]}
    end,
    intensity=function(l)
        assert(owned[l.owner],'read a light not owned by the probe')
        getter_calls.intensity=getter_calls.intensity+1
        return l.intensity
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
    def test_idle_native_probe_does_not_enumerate_worlds_or_touch_lights(self):
        replay(FLAT+MENU+NATIVE+'''
local worlds=sr.Application.worlds
local world_reads=0
sr.Application.worlds=function(...)
    world_reads=world_reads+1
    return worlds(...)
end
local probe=assert(require('mods/codex/eagle_native_light_probe').new(sr))
local catalog=require('mods/codex/eagle_stratagem_profiles').catalog
for i=1,12 do
    local active,status,count=probe:sync(WORLD,{},i*0.05,false,i)
    assert(not active and status=='idle' and count==0)
    probe:keep_alive({},catalog,i,i*0.05,'epoch')
end
probe:release()
assert(world_reads==0 and spawned==0 and setter_calls.enabled_true==0
    and setter_calls.color==0 and setter_calls.intensity==0,
    'idle native probe performed unnecessary world or light calls')
''')

    def test_owned_target_light_is_reasserted_each_render_frame_and_stops_with_guide(self):
        replay(FLAT+MENU+NATIVE+'''
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
M.show_air=false;M.show_sky=false;M.show_ground_border=false
M.show_ground_triangles=false;M.show_ground_area=false;M.show_cordon=false
local before=setter_calls.enabled_true
frames(6)
assert(setter_calls.enabled_true==before+6,
    'active target light was not reasserted once per rendered frame')
        M.native_dirty=false
        native_sync_next=FAKE_TIME*1000+5000
        M.impacts={};M.impact_order={}
local retired=setter_calls.enabled_true
frames(4)
assert(live_count()==0 and setter_calls.enabled_true==retired,
    'keepalive continued after its confirmed guide retired between sync polls')
M.native_dirty=true
frames(3)
assert(setter_calls.enabled_true==retired,
    'no-guide frames still called the native light setter')
''')

    def test_keepalive_failure_cleans_only_the_owned_helper(self):
        replay(FLAT+MENU+NATIVE+'''
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(live_count()==1 and setter_calls.enabled_true>0)
enabled_failure=true
frames(1)
assert(live_count()==0 and removed==1 and spawned==1,
    'failed keepalive did not fail closed on the owned helper')
assert(M.native_light_status:find('keepalive failed',1,true),
    'keepalive failure was not exposed in status')
enabled_failure=false
apply('show_native_light_probe',false);frames(1)
assert(spawned==1,'disable after failure recreated a helper')
''')

    def test_partial_spawn_failure_honors_retry_backoff_but_keeps_existing_light_alive(self):
        replay(FLAT+MENU+NATIVE+'''
local probe=assert(require('mods/codex/eagle_native_light_probe').new(sr))
local catalog={[18]=true}
local first={p={0,0,0},stratagem_type=18,type_epoch='epoch'}
local second={p={80,20,0},stratagem_type=18,type_epoch='epoch'}
local impacts={[1]=first}
local active,status,count=probe:sync(WORLD,impacts,0,true,1)
assert(active and count==1 and spawned==1,'authored mode did not establish the first helper')
impacts[2]=second;setup_failure=true
active,status,count=probe:sync(WORLD,impacts,0.05,true,2)
assert(spawned==2 and count==1 and live_count()==1 and probe.retry_at==1.05,
    'second-helper setup failure did not preserve the first helper and set retry backoff')
assert(status:find('unavailable',1,true),'partial setup failure was not reported')
setup_failure=false
active,status,count=probe:sync(WORLD,impacts,0.1,true,3)
assert(spawned==2 and active and count==1,
    'retry backoff did not suppress helper creation before its deadline')
local keeps=setter_calls.enabled_true
active,status,count=probe:keep_alive(impacts,catalog,4,0.15,'epoch')
assert(active and count==1 and setter_calls.enabled_true==keeps+1,
    'retry backoff stopped per-frame keepalive for the surviving helper')
probe:release()
assert(live_count()==0 and removed==spawned,'partial setup recovery leaked helpers')
''')

    def test_authored_light_option_skips_color_intensity_and_rebuilds_owned_helper(self):
        replay(FLAT+MENU+NATIVE+'''
saved['eagle_direction_probe.show_native_light_probe']=true
saved['eagle_direction_probe.native_light_authored_color']=true
frames(50)
assert(spawned==1 and live_count()==1,'authored-color mode did not create one helper')
local first=next(owned)
local light=first.lights[0]
assert(light.enabled and light.rgb[1]==9000 and light.rgb[2]==8550
    and light.rgb[3]==7560 and light.intensity==1,
    'authored mode changed the bundled resource light values')
assert(setter_calls.color==0 and setter_calls.intensity==0,
    'authored mode called a color or intensity setter')
local diagnostic=M.native_light_probe.color_diagnostic
assert(diagnostic:find('setters_skipped=true',1,true)
    and diagnostic:find('mode=authored',1,true),
    'authored readback did not identify skipped setters')
local removed_before_toggle=removed
apply('native_light_authored_color',false)
assert(removed==removed_before_toggle and live_count()==1,
    'MOM callback performed engine cleanup instead of marking the next draw dirty')
frames(1)
assert(removed==1 and spawned==2 and live_count()==1,
    'changing color mode did not retire/recreate only the owned helper')
local second
for unit in pairs(owned) do if unit.alive then second=unit end end
local purple=second.lights[0]
assert(purple.rgb[1]==1 and purple.rgb[2]==0 and purple.rgb[3]==1
    and purple.intensity==7000,
    'switching back to purple did not apply the original prototype settings')
assert(setter_calls.color==1 and setter_calls.intensity==1,
    'switching color mode did not reapply exactly one setter pair')
assert(getter_calls.color==4 and getter_calls.intensity==4,
    'each world/mode should capture readback once on its first successful helper')
assert(M.native_light_probe.color_diagnostic:find('mode=purple',1,true)
    and M.native_light_probe.color_diagnostic:find('setters_skipped=false',1,true),
    'purple mode readback was not refreshed after authored mode')
''')

    def test_transform_is_committed_then_read_back_on_spawn_and_real_moves(self):
        replay(FLAT+MENU+NATIVE+'''
local events={}
local world_position_reads,basis_reads=0,0
local set_position=sr.Unit.set_local_position
local set_rotation=sr.Unit.set_local_rotation
local original_world_position=sr.Unit.world_position
local original_world_pose=sr.Unit.world_pose
sr.Unit.set_local_position=function(u,node,v)
    set_position(u,node,v)
    u.pending_p={v[1],v[2],v[3]};u.p=nil
    events[#events+1]='position'
end
sr.Unit.set_local_rotation=function(u,node,q)
    set_rotation(u,node,q)
    u.pending_q=q;u.q=nil
    events[#events+1]='rotation'
end
sr.World.update_unit=function(world,u)
    assert(world==WORLD)
    if not owned[u] then return end
    u.p=u.pending_p;u.q=u.pending_q
    events[#events+1]='update'
end
sr.Unit.world_position=function(u,node)
    if not owned[u] then return original_world_position(u,node) end
    assert(node==0 and u.p,'position read before committed world update')
    world_position_reads=world_position_reads+1
    events[#events+1]='world_position'
    return {u.p[1],u.p[2],u.p[3]}
end
sr.Unit.world_pose=function(u,node)
    if not owned[u] then return original_world_pose(u,node) end
    assert(node==0 and u.q,'pose read before committed world update')
    basis_reads=basis_reads+1
    events[#events+1]='world_pose'
    return u.q
end
sr.Matrix4x4={forward=function(q)
    assert(q.angle and math.abs(q.angle+math.pi/2)<0.0001)
    return {0,0,-1}
end}
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
local u=next(owned)
local impact=M.impacts[1].p
assert(spawned==1 and u.p[1]==impact[1] and u.p[2]==impact[2] and u.p[3]==impact[3]+12,
    'spawn transform was not committed before position readback: '..tostring(u.p and table.concat(u.p,','))
        ..' expected '..table.concat({impact[1],impact[2],impact[3]+12},','))
assert(table.concat(events,',')=='rotation,position,update,world_position,world_pose',
    'initial transform must be set, committed, then read back: '..table.concat(events,','))
local diagnostic=M.native_light_probe.color_diagnostic
local expected=string.format('expected_pos=%.6g,%.6g,%.6g',impact[1],impact[2],impact[3]+12)
assert(diagnostic and diagnostic:find(expected,1,true)
    and diagnostic:find('world_pos='..string.format('%.6g,%.6g,%.6g',u.p[1],u.p[2],u.p[3]),1,true)
    and diagnostic:find('root_forward=0,0,-1',1,true),
    'first owned helper transform was not captured: '..tostring(diagnostic))
assert(world_position_reads==1 and basis_reads==1,
    'first helper/world transform readback should happen exactly once')
events={}
M.impacts[1].p={5,6,7};frames(1)
assert(table.concat(events,',')=='position,update',
    'later movement should commit without another diagnostic read: '..table.concat(events,','))
assert(world_position_reads==1 and basis_reads==1,
    'same-world helper movement repeated first-helper readback')
events={};frames(1)
assert(#events==0,'stationary helper should not update or read its transform again')
shutdown()
''')

    def test_transform_getter_failures_are_optional_and_never_block_owned_helper(self):
        replay(FLAT+MENU+NATIVE+'''
local original_world_position=sr.Unit.world_position
sr.Unit.world_position=function(u,node)
    if owned[u] then error('unsupported helper node signature') end
    return original_world_position(u,node)
end
sr.Unit.world_pose=nil
sr.Matrix4x4=nil
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(live_count()==1 and M.native_light_status=='native violet spotlight test active (prototype)',
    'optional transform getter failures blocked helper creation')
local diagnostic=M.native_light_probe.color_diagnostic
assert(diagnostic and diagnostic:find('world_pos=error',1,true)
    and diagnostic:find('root_forward=unavailable',1,true),
    'optional pose API failures were not identified in readback')
shutdown()
assert(live_count()==0 and removed==1,'shutdown left a helper after optional pose getters were absent')
''')

    def test_failed_first_helper_setup_does_not_consume_world_readback(self):
        replay(FLAT+MENU+NATIVE+'''
failures=true
local original_world_position=sr.Unit.world_position
local world_reads=0
sr.Unit.world_position=function(u,node)
    if owned[u] then
        world_reads=world_reads+1
        return {u.p[1],u.p[2],u.p[3]}
    end
    if original_world_position then return original_world_position(u,node) end
    return nil
end
saved['eagle_direction_probe.show_native_light_probe']=true
frames(70)
assert(M.native_light_probe and not M.native_light_probe.diagnostic_reported
    and M.native_light_probe.color_diagnostic==nil,
    'failed helper setup consumed the first-successful diagnostic')
failures=false
frames(80)
assert(live_count()==1 and M.native_light_probe.diagnostic_reported
    and M.native_light_probe.color_diagnostic,
    'first later successful helper did not produce the world diagnostic')
assert(world_reads==1,'failed setup read transform or repeated first-successful readback')
shutdown()
assert(live_count()==0 and removed==spawned,'failed/successful helper sequence leaked units')
''')

    def test_violet_comparison_uses_purple_color_at_unchanged_intensity(self):
        replay(FLAT+MENU+NATIVE+'''
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(spawned==1 and live_count()==1,'native helper did not spawn')
local u=next(owned)
local light=sr.Unit.light(u,'helmet_headlamp_task_fill')
assert(light.rgb[1]==1 and light.rgb[2]==0 and light.rgb[3]==1,
    'violet comparison must use normalized purple RGB')
assert(light.intensity==7000,'violet comparison changed the fixed intensity')
assert(getter_calls.color==2 and getter_calls.intensity==2,
    'color and intensity should be read once before and after helper setup only')
local diagnostic=M.native_light_probe and M.native_light_probe.color_diagnostic
assert(diagnostic and diagnostic:find('before_color=',1,true)
    and diagnostic:find('after_color=',1,true),
    'owned helper readback was not retained for the main log: '..tostring(diagnostic))
shutdown()
assert(live_count()==0 and removed==1,'shutdown left a native light behind')
''')

    def test_optional_color_getter_failures_do_not_block_the_native_light(self):
        replay(FLAT+MENU+NATIVE+'''
sr.Light.color=function() error('getter signature mismatch') end
sr.Light.intensity=function() error('getter signature mismatch') end
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(live_count()==1 and M.native_light_status=='native violet spotlight test active (prototype)',
    'diagnostic getter errors blocked an otherwise configured light')
shutdown()
assert(live_count()==0 and removed==1,'shutdown left the native light alive')
''')

    def test_missing_set_intensity_is_reported_and_never_spawns_a_white_helper(self):
        replay(FLAT+MENU+NATIVE+'''
sr.Light.set_intensity=nil
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(spawned==0,'helper spawned without the intensity setter needed for normalized color')
assert(M.native_light_status:find('Light.set_intensity',1,true),
    'missing intensity setter was not explained')
''')

    def test_optional_light_lookup_apis_can_be_missing_with_safe_named_light_cleanup(self):
        replay(FLAT+MENU+NATIVE+'''
sr.Unit.num_lights=nil
sr.Unit.has_light=nil
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(spawned==1 and live_count()==1,'optional API absence blocked named-light setup')
assert(#M.seg>0,'missing optional APIs broke existing guide drawing')
local u=next(owned)
local lit=0
for _,l in pairs(u.lights) do if l.enabled then
    lit=lit+1
    assert(l==u.lights[0],'an unrelated resource light stayed enabled')
end end
assert(lit==1,'named-light setup did not leave only task fill active')
shutdown()
assert(live_count()==0 and removed==1,'named-light cleanup left a helper alive')
''')

    def test_missing_required_apis_are_reported_together(self):
        replay(FLAT+MENU+NATIVE+'''
sr.Light.set_color=nil
sr.Unit.set_unit_visibility=nil
sr.World.update_unit=nil
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(spawned==0,'helper spawned with required APIs missing')
local status=M.native_light_status
assert(status:find('Light.set_color',1,true),'first missing API was omitted from reason')
assert(status:find('Unit.set_unit_visibility',1,true),'second missing API was omitted from reason')
assert(status:find('World.update_unit',1,true),'required transform commit API was omitted from reason')
''')

    def test_update_unit_errors_fail_closed_and_clean_up_owned_helpers(self):
        replay(FLAT+MENU+NATIVE+'''
sr.World.update_unit=function() error('unsupported signature') end
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(spawned>0 and live_count()==0 and removed==spawned,
    'helper survived a failed transform commit')
assert(M.native_light_status:find('native light unavailable',1,true),
    'transform commit failure was not exposed')
assert(#M.seg>0,'transform commit failure disabled existing corridor drawing')
''')

    def test_present_but_wrong_num_lights_rejects_the_resource_profile(self):
        replay(FLAT+MENU+NATIVE+'''
sr.Unit.num_lights=function() return 4 end
saved['eagle_direction_probe.show_native_light_probe']=true
frames(60)
assert(M.native_light_status:find('headlamp resource profile unavailable',1,true),
    'wrong resource light count was not rejected: '..M.native_light_status)
assert(live_count()==0,'wrong resource light count leaked a helper')
assert(M.native_light_status:find('unavailable',1,true),'wrong resource count reason missing')
''')

    def test_missing_spot_angle_setters_preserve_the_resource_cone_and_still_light(self):
        for missing in (
            'sr.Light.set_spot_angle_start=nil;sr.Light.set_spot_angle_end=nil',
            'sr.Light.set_spot_angle_start=nil',
        ):
            with self.subTest(missing=missing):
                replay(FLAT+MENU+NATIVE+missing+'''
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(spawned==1 and live_count()==1,'optional spot-angle API blocked native light creation')
local u=next(owned)
local lit=0
for _,l in pairs(u.lights) do if l.enabled then lit=lit+1 end end
assert(lit==1,'resource default cone did not remain enabled')
local light=sr.Unit.light(u,'helmet_headlamp_task_fill')
assert(light.inner==1.92 and light.outer==2.79 and light.reach==30,
    'prototype modified the resource-authored cone or falloff')
assert(M.native_light_status=='native violet spotlight test active (prototype)',
    'native light did not report active with its resource cone')
shutdown()
assert(live_count()==0 and removed==1,'shutdown left the native light helper alive')
''')

    def test_saved_toggle_creates_real_light_only_in_own_helper_without_red_face_overlay(self):
        replay(FLAT+MENU+NATIVE+'''
frames(50)
assert(spawned==0,'prototype created lights by default')
local queries=casts
apply('show_native_light_probe',true);frames(1)
assert(spawned==1 and live_count()==1,
    'native light prototype did not create a helper: '..tostring(M.native_light_status))
local u=next(owned)
assert(u.hidden and u.p[1]==0 and u.p[2]==0 and u.p[3]==12,'emitter not above actual beacon')
local lit=0
for _,l in pairs(u.lights) do if l.enabled then
    lit=lit+1
    assert(l.rgb[1]==1 and l.rgb[2]==0 and l.rgb[3]==1 and l.intensity==7000,
        'prototype did not use purple RGB at the fixed intensity')
    assert(l.inner==1.92 and l.outer==2.79 and l.reach==30,
        'resource-authored cone/falloff was changed')
    assert(l.shadows and l.volumetric,'resource-authored lighting flags were changed')
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

    def test_unverified_render_flag_setters_cannot_block_a_usable_light(self):
        replay(FLAT+MENU+NATIVE+'''
sr.Light.set_casts_shadows=function() error('unsupported signature') end
sr.Light.set_volumetric_enabled=function() error('unsupported signature') end
saved['eagle_direction_probe.show_native_light_probe']=true
frames(50)
assert(spawned==1 and live_count()==1,'unverified render flag setter blocked native light')
assert(M.native_light_status=='native violet spotlight test active (prototype)')
shutdown()
assert(live_count()==0 and removed==1,'shutdown left the native light helper alive')
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
assert(live_count()==0 and removed==1,'native violet test outlived guide')
''')

    def test_many_guides_create_at_most_one_helper_per_frame_without_a_count_cap(self):
        replay(FLAT+MENU+NATIVE+'''
frames(50)
for i=2,8 do
    M.impacts[i]={p={i*10,0,0},heading={1,0,0},aircraft='design',beacon=BEACON,
        last_seen=FAKE_TIME+1000,t=FAKE_TIME}
end
-- These are renderer/lifecycle fixture guides, not classification cases.
M.type_profiles=require('mods/codex/eagle_stratagem_profiles')
M.type_world=WORLD;M.type_epoch=tostring(WORLD)..':mission-one'
for _,imp in pairs(M.impacts) do
    imp.stratagem_type=18;imp.type_epoch=M.type_epoch;imp.type_heading_confirmed=true
end
apply('show_native_light_probe',true)
for i=1,10 do local n=spawned;frames(1);assert(spawned-n<=1,'light creation burst exceeded budget') end
assert(live_count()==8,'native light guide count capped')
assert(getter_calls.color==2 and getter_calls.intensity==2,
    'same-world helper creation repeated the one-time readback diagnostic')
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
