"""World-space true faces, tested against the audited HD2 Lua binding semantics."""
import unittest
from pathlib import Path

from test_mission_feedback import replay
from test_terrain_query import SCENE
from test_departure_options_performance import MENU


GUI = '''
local faces,creates,updates,destroys,gui_creates,gui_destroys={},0,0,0,0,0
local next_id=0
sr.Matrix4x4.identity=function() return {identity=true} end
sr.World.create_world_gui=function(world,pose,w,h,...)
    assert(world==WORLD and pose.identity and w==1 and h==1 and select('#',...)==0,
        'wrong audited world GUI signature')
    gui_creates=gui_creates+1
    return {world=world}
end
sr.World.destroy_gui=function(world,gui)
    assert(world==WORLD and gui.world==world,'stale world GUI destruction')
    faces={}
    gui_destroys=gui_destroys+1
end
sr.Gui.triangle=function(gui,a,b,c,layer,color,...)
    assert(gui.world==WORLD and layer==100 and color and select('#',...)==0)
    next_id=next_id+1;creates=creates+1
    -- HD2 creation swaps Y/Z before storing the vertices.
    faces[next_id]={{a[1],a[3],a[2]},{b[1],b[3],b[2]},{c[1],c[3],c[2]}}
    return next_id
end
sr.Gui.update_triangle=function(gui,id,a,b,c,layer,color)
    assert(faces[id] and gui.world==WORLD and layer==100 and color)
    updates=updates+1
    faces[id]={{a[1],a[2],a[3]},{b[1],b[2],b[3]},{c[1],c[2],c[3]}}
end
sr.Gui.destroy_triangle=function(gui,id)
    assert(faces[id] and gui.world==WORLD)
    faces[id]=nil;destroys=destroys+1
end
package.preload['mods/codex/eagle_solid_renderer']=function()
    local path=os.getenv('DSH_PROBE_PATH'):gsub('eagle_direction_probe.lua$','solid_renderer.lua')
    return assert(loadfile(path))()
end
'''


class SolidRendererTest(unittest.TestCase):
    def test_retained_faces_use_correct_create_update_coordinates_and_both_windings(self):
        replay(GUI + '''
local R=require('mods/codex/eagle_solid_renderer')
local r=assert(R.new(sr))
assert(gui_creates==0,'native GUI created during module loading')
local first={{'air',{1,2,3},{4,2,3},{1,5,6}}}
local colors={air=sr.Color(255,255,255,255)}
assert(r:submit(WORLD,first,{},colors))
assert(gui_creates==1 and creates==2,'one triangle requires two opposed faces')
assert(faces[1][1][2]==2 and faces[1][1][3]==3,'creation did not compensate Y/Z swap')
assert(faces[2][2][1]==1 and faces[2][2][2]==5,'reverse winding missing')
local second={{'air',{9,8,7},{4,2,3},{1,5,6}}}
local empty={}
assert(r:submit(WORLD,second,empty,colors))
assert(creates==2 and updates==2 and faces[1][1][2]==8 and faces[1][1][3]==7,
    'updates recreated faces or incorrectly swapped XYZ')
assert(r:submit(WORLD,second,empty,colors))
assert(updates==2,'unchanged references caused native triangle updates')
r:clear()
assert(destroys==2 and next(faces)==nil,'clear left retained faces behind')
r:release()
assert(gui_destroys==1,'world GUI not released')
''')

    def test_real_guides_contain_faces_instead_of_scan_fill_and_keep_terrain_budget(self):
        replay(GUI + SCENE + '''
frames(45)
assert(M.solid_active and creates>0,'true-fill renderer was not activated')
local kinds={}
for _,batch in ipairs({M.seg,M.flow_seg}) do
    for _,s in ipairs(batch) do
        if s[4] then
            kinds[s[1]]=true
            for k=2,4 do
                for j=1,3 do assert(type(s[k][j])=='number','missing triangle vertex') end
            end
        elseif s[1]=='air' or s[1]=='flow' or s[1]:match('^sky%d$') or s[1]=='cordon_dim' then
            error('scan-line filling survived true-fill mode')
        end
    end
end
assert(kinds.air and kinds.flow and kinds.sky1 and kinds.marker and kinds.cordon_dim,
    'air/ground/sky/diamond/panels were not converted to real faces')
assert(max_frame<=2,'true fill added terrain collision queries')
assert(M.seg_count<600,'true fill failed to reduce geometric primitives')
local q,old=casts,updates
frames(5)
assert(casts==q and updates>old,'moving faces froze or re-queried terrain')
''')

    def test_saved_switch_and_depth_mode_fall_back_without_ghost_faces(self):
        replay(GUI + SCENE + MENU + '''
frames(45)
local row=rows['eagle_direction_probe.solid_fill']
assert(row and row.default and M.solid_active,'saved true-fill control missing')
apply('solid_fill',false);frames(1)
assert(not M.solid_active and next(faces)==nil,'disable left true faces behind')
apply('solid_fill',true);frames(1)
assert(M.solid_active and next(faces),'true fill failed to return')
apply('through_world',true);frames(1)
assert(not M.solid_active and next(faces)==nil,'x-ray compatibility fallback missing')
apply('through_world',false);frames(1)
assert(M.solid_active and next(faces),'depth-tested fill did not return')
M.tracks={};M.track_order={};M.impacts={};frames(1)
assert(next(faces)==nil,'retired strike left retained faces')
''')

    def test_missing_world_api_uses_original_line_fill(self):
        replay(GUI + SCENE + '''
sr.World.create_world_gui=nil
frames(45)
assert(not M.solid_active and gui_creates==0,'missing API called a native constructor')
local scan=false
for _,s in ipairs(M.flow_seg) do if s[1]=='flow' and not s[4] then scan=true end end
assert(scan and M.seg_count>600,'missing API removed existing line guides')
''')

    def test_invalid_or_disappeared_world_is_never_passed_to_gui_native_calls(self):
        replay(GUI + '''
local R=require('mods/codex/eagle_solid_renderer')
local r=assert(R.new(sr))
local tri={{'air',{1,2,3},{4,2,3},{1,5,6}}}
assert(not r:submit({},tri,{}, {air=sr.Color(255,255,255,255)}))
assert(gui_creates==0,'unknown world created a GUI')
assert(r:submit(WORLD,tri,{}, {air=sr.Color(255,255,255,255)}))
sr.Application.worlds=function() return {} end
r:release()
assert(gui_destroys==0 and destroys==0,'release used vanished world handles')
''')

    def test_bad_faces_are_rejected_and_shrinking_batches_remove_surplus(self):
        replay(GUI + '''
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local color={air=sr.Color(255,255,255,255)}
assert(not r:submit(WORLD,{{'air',{0/0,0,0},{1,0,0},{0,1,0}}},{},color))
assert(gui_creates==0,'bad vertex reached native constructor')
local t={'air',{0,0,0},{1,0,0},{0,1,0}}
assert(r:submit(WORLD,{t,t},{},color))
assert(creates==4)
assert(r:submit(WORLD,{t},{},color))
assert(destroys==2 and r.count==2,'surplus retained faces survived shrinking')
''')

    def test_lua_triangle_failure_recovers_line_fill_on_the_next_frame(self):
        replay(GUI + SCENE + '''
sr.Gui.triangle=function() error('simulated binding failure') end
frames(45)
assert(M.solid_failed and not M.solid_active and next(faces)==nil,
    'failed triangle path left active true fill')
local scan=false
for _,s in ipairs(M.flow_seg) do if s[1]=='flow' and not s[4] then scan=true end end
assert(scan and FRAME_HAS_LINES,'line fallback did not recover after Lua failure')
''')

    def test_140_fps_does_not_update_retained_faces_on_unchanged_frames(self):
        replay(GUI + SCENE + '''
frames(45)
local q,before,changed=casts,updates,0
for i=1,140 do
    FAKE_TIME=FAKE_TIME+1/140
    local old=updates
    update()
    if updates>old then changed=changed+1 end
end
assert(changed>=19 and changed<=21,'face updates were not cached at 20 Hz')
assert(updates>before and casts==q,'retained animation froze or queried terrain')
''')


if __name__=='__main__':
    unittest.main()
