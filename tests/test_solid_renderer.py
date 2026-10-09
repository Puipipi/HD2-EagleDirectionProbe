"""World-space faces through both HD2 wrapper and final native vertex conversion."""
import unittest
from pathlib import Path

from test_mission_feedback import replay, THROW
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
    -- Creation wrapper swaps Y/Z, then the shared native vertex writer swaps back.
    -- Earlier fixtures incorrectly stopped at the intermediate wrapper structure.
    local function vertex(v)
        local wrapped={v[1],v[3],v[2]}
        return {wrapped[1],wrapped[3],wrapped[2]}
    end
    faces[next_id]={vertex(a),vertex(b),vertex(c)}
    return next_id
end
sr.Gui.update_triangle=function(gui,id,a,b,c,layer,color)
    assert(faces[id] and gui.world==WORLD and layer==100 and color)
    updates=updates+1
    -- Update wrapper copies XYZ unchanged, then uses the same native writer.
    faces[id]={{a[1],a[3],a[2]},{b[1],b[3],b[2]},{c[1],c[3],c[2]}}
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
    def test_real_cordon_producer_keeps_one_readable_copy_per_panel(self):
        prelude = '''
POSE_CALLS=0;POSE_BUCKET=nil;POSE_POINT={x=0,y=100,z=0}
POSE_FIXTURE={new=function()
    return {sample=function(_,world,now)
        local bucket=math.floor(now*10)
        if bucket~=POSE_BUCKET then POSE_BUCKET=bucket;POSE_CALLS=POSE_CALLS+1 end
        return POSE_POINT,'OK','network_avatar'
    end}
end}
'''
        replay(prelude=prelude, scene=GUI + THROW + '''
M.show_cordon=true;M.show_ground_border=true;M.solid_fill=true;M.solid_failed=false
M.solid_active=true;M.show_type=false
local function frames(n) for _=1,n do tick(1) end end
local before_pose=POSE_CALLS
local font=require('mods/codex/eagle_cordon_font')
local label='EAGLE ?';local bars=0
for i=1,#label do local glyph=font.get(label:sub(i,i));if glyph then bars=bars+#glyph end end
local function check(viewer_y)
    local texts,index=0,0
    for _,batch in ipairs({M.seg,M.flow_seg}) do
        for _,s in ipairs(batch) do
            if s[4] then
                index=index+1
                if s[1]=='cordon_text' then
                    texts=texts+1
                    local f=faces[M.solid_renderer.ids[index]]
                    local a,b,c=f[1],f[2],f[3]
                    local abx,abz=b[1]-a[1],b[3]-a[3]
                    local acx,acz=c[1]-a[1],c[3]-a[3]
                    local ny=abz*acx-abx*acz
                    assert(ny*viewer_y>0,
                        'selected text triangle must face its viewer after renderer winding')
                else index=index+1 end
            end
        end
    end
    assert(texts==bars*6*2,'all six panels need one complete solid label, got '..texts
        ..' expected '..(bars*6*2)..' show_type='..tostring(M.show_type))
end
frames(4);check(1)
assert(POSE_CALLS-before_pose<=3,'pose resolver did not reuse its 10 Hz cache: '..POSE_CALLS)
POSE_POINT={x=0,y=-100,z=0};M.flow_key=nil;M.cordon_key=nil;M.geom_key=nil
frames(4);check(-1)
M.solid_fill=false;M.cordon_key=nil;M.flow_key=nil
frames(2)
local fallback_text=0
local saw_inner,saw_outer=false,false
local first=next(M.impacts);local imp=first and M.impacts[first]
local hx,hy=imp.heading[1],imp.heading[2];local len=math.sqrt(hx*hx+hy*hy);hx,hy=hx/len,hy/len
local face_half=M.type_profiles.bounds(imp.stratagem_type).half
for _,s in ipairs(M.flow_seg) do if s[1]=='cordon_text' then
    fallback_text=fallback_text+1
    for k=2,3 do
        local p=s[k]
        local lateral=(p[1]-imp.p[1])*(-hy)+(p[2]-imp.p[2])*hx
        if math.abs(math.abs(lateral)-(face_half+0.04))<0.001 then saw_outer=true
        elseif math.abs(math.abs(lateral)-(face_half-0.04))<0.001 then saw_inner=true
        else error('line fallback selected an unrecognized text face offset: '..lateral) end
    end
end end
assert(fallback_text==bars*6,'line fallback should keep one readable copy per panel: '..fallback_text)
assert(saw_inner and saw_outer,'line fallback did not keep selected inner and outer faces')
''')

    def test_circle_panel_side_minus_one_uses_its_nonzero_radial_angle(self):
        prelude = '''
POSE_POINT={x=0,y=100,z=0}
POSE_FIXTURE={new=function() return {sample=function() return POSE_POINT,'OK','network_avatar' end} end}
local path=os.getenv('DSH_PROBE_PATH'):gsub('eagle_direction_probe.lua$','cordon_view.lua')
local real=assert(loadfile(path))();CORDON_VIEW_CALLS={}
CORDON_VIEW_FIXTURE={choose=function(viewer,center,normal,last)
    local chosen=real.choose(viewer,center,normal,last)
    CORDON_VIEW_CALLS[#CORDON_VIEW_CALLS+1]={center={center[1],center[2],center[3]},
        normal={normal[1],normal[2],normal[3]},side=chosen}
    return chosen
end}
'''
        flat=SCENE.replace("return math.max(0, 30 - math.abs(x - 60)), 'HIT'", "return 0, 'HIT'")
        replay(prelude=prelude, scene=GUI + flat + THROW + '''
M.show_cordon=true;M.show_ground_border=true;M.solid_fill=true;M.solid_failed=false
M.solid_active=true;M.show_type=false
local imp=M.impacts[next(M.impacts)]
imp.stratagem_type=3;imp.type_heading_confirmed=true;imp.type_epoch=M.type_epoch
M.type_next=FAKE_TIME*1000+5000
M.geom_key=nil;M.flow_key=nil;M.cordon_key=nil;M.ground_geom_key=nil
CORDON_VIEW_CALLS={}
for _=1,4 do tick(1) end
local radial=false
for _,row in ipairs(CORDON_VIEW_CALLS) do
    local nx,ny=row.normal[1],row.normal[2]
    if nx>0.4 and ny< -0.2 then
        radial=true
        assert(row.side=='inner','circle side -1 at nonzero angle must choose its viewer-facing inner copy')
        local dx,dy=row.center[1]-imp.p[1],row.center[2]-imp.p[2]
        assert(math.abs(dx-nx)<0.001 and math.abs(dy-ny)<0.001,
            'circle selection normal must be the actual radial vector from its panel center')
    end
end
assert(radial,'circle producer did not exercise side -1 at a nonzero radial angle')
local index=0
for _,batch in ipairs({M.seg,M.flow_seg}) do
    for _,s in ipairs(batch) do
        if s[4] then
            index=index+1
            if s[1]=='cordon_text' then
                local f=faces[M.solid_renderer.ids[index]]
                local a,b,c=f[1],f[2],f[3]
                local abx,aby,abz=b[1]-a[1],b[2]-a[2],b[3]-a[3]
                local acx,acy,acz=c[1]-a[1],c[2]-a[2],c[3]-a[3]
                local nx=aby*acz-abz*acy;local ny=abz*acx-abx*acz
                local cx=(a[1]+b[1]+c[1])/3;local cy=(a[2]+b[2]+c[2])/3
                assert(nx*(0-cx)+ny*(100-cy)>0,
                    'circle lettering must face the actual viewer ray after renderer winding')
            end
            index=index+(s[1]=='cordon_text' and 0 or 1)
        end
    end
end
''')

    def test_unchanged_immutable_batches_are_not_rescanned_each_frame(self):
        replay(GUI + '''
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local p={1,2,3}
local static={{'air',p,{4,2,3},{1,5,6}}}
local flow={}
local colors={air=sr.Color(255,255,255,255)}
assert(r:submit(WORLD,static,flow,colors))
-- The public batch references promise immutable geometry. Instrument reads of
-- the original point to detect redundant validation on a retained-only frame.
local backup={p[1],p[2],p[3]}
for i=1,3 do p[i]=nil end
setmetatable(p,{__index=function(_,i) error('unchanged vertex was rescanned') end})
assert(r:submit(WORLD,static,flow,colors))
assert(updates==0 and creates==2)
setmetatable(p,nil)
for i=1,3 do p[i]=backup[i] end
''')

    def test_same_world_same_batches_skip_world_and_triangle_native_calls(self):
        replay(GUI + '''
local world_reads=0
local worlds=sr.Application.worlds
sr.Application.worlds=function() world_reads=world_reads+1;return worlds() end
local vector=sr.Vector3
local vector_calls=0
sr.Vector3=function(...) vector_calls=vector_calls+1;return vector(...) end
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local static={{'air',{1,2,3},{4,2,3},{1,5,6}}}
local flow={{'air',{11,12,13},{14,12,13},{11,15,16}}}
local colors={air=sr.Color(255,255,255,255)}
assert(r:submit(WORLD,static,flow,colors))
world_reads,vector_calls,creates,updates,destroys=0,0,0,0,0
assert(r:submit(WORLD,static,flow,colors))
assert(world_reads==0,'unchanged retained batches still enumerated worlds')
assert(vector_calls==0 and creates==0 and updates==0 and destroys==0,
    'unchanged retained batches made native geometry calls')
''')

    def test_dead_world_same_batch_fastpath_is_inert_then_changed_batch_releases_safely(self):
        replay(GUI + '''
local expected_world=WORLD
local world_reads=0
local worlds=sr.Application.worlds
sr.Application.worlds=function() world_reads=world_reads+1;return worlds() end
sr.World.create_world_gui=function(world,pose,w,h,...)
    assert(world==expected_world and pose.identity and w==1 and h==1 and select('#',...)==0,
        'new GUI used the wrong world or signature')
    gui_creates=gui_creates+1
    return {world=world}
end
sr.World.destroy_gui=function(world,gui)
    assert(world==expected_world,'destroyed GUI through the wrong world')
    faces={};gui_destroys=gui_destroys+1
end
sr.Gui.triangle=function(gui,a,b,c,layer,color)
    assert(gui.world==expected_world and layer==100 and color)
    next_id=next_id+1;creates=creates+1
    faces[next_id]={a,b,c};return next_id
end
sr.Gui.update_triangle=function(gui,id,a,b,c,layer,color)
    assert(gui.world==expected_world and faces[id] and layer==100 and color)
    updates=updates+1;faces[id]={a,b,c}
end
sr.Gui.destroy_triangle=function(gui,id)
    assert(gui.world==expected_world and faces[id])
    faces[id]=nil;destroys=destroys+1
end
local vector=sr.Vector3
local vector_calls=0
sr.Vector3=function(...) vector_calls=vector_calls+1;return vector(...) end
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local original={{'air',{1,2,3},{4,2,3},{1,5,6}}}
local empty={}
local colors={air=sr.Color(255,255,255,255)}
assert(r:submit(WORLD,original,empty,colors))
world_reads,vector_calls,creates,updates,destroys,gui_destroys=0,0,0,0,0,0
sr.Application.worlds=function() world_reads=world_reads+1;return {} end
assert(r:submit(WORLD,original,empty,colors),'same-batch no-op should remain inert for a vanished world')
assert(world_reads==0 and vector_calls==0 and creates==0 and updates==0 and destroys==0
    and gui_destroys==0,'same-batch fastpath touched a stale native handle')
local changed={{'air',{2,3,4},{5,3,4},{2,6,7}}}
local accepted,reason=r:submit(WORLD,changed,{},colors)
assert(not accepted and reason=='world unavailable','changed batch did not validate vanished world')
assert(world_reads>0 and gui_destroys==0 and destroys==0,
    'changed batch failed to detect dead world or destroyed through its stale GUI')
local WORLD2={name='world-2'}
expected_world=WORLD2
sr.Application.worlds=function() return {WORLD2} end
assert(r:submit(WORLD2,changed,{},colors),'new live world did not rebuild its GUI')
assert(gui_creates==2 and creates==2 and gui_destroys==0,
    'new world did not create fresh opposed faces after stale release: gui='..gui_creates
        ..' faces='..creates..' gui_destroy='..gui_destroys)
''')

    def test_retained_faces_use_correct_create_update_coordinates_and_both_windings(self):
        replay(GUI + '''
local R=require('mods/codex/eagle_solid_renderer')
local r=assert(R.new(sr))
assert(gui_creates==0,'native GUI created during module loading')
local first={{'air',{1,2,3},{4,2,3},{1,5,6}}}
local colors={air=sr.Color(255,255,255,255)}
assert(r:submit(WORLD,first,{},colors))
assert(gui_creates==1 and creates==2,'one triangle requires two opposed faces')
assert(faces[1][1][2]==2 and faces[1][1][3]==3,'created face exchanged world distance and height')
assert(faces[2][2][1]==1 and faces[2][2][2]==5,'reverse winding missing')
local second={{'air',{9,8,7},{4,2,3},{1,5,6}}}
local empty={}
assert(r:submit(WORLD,second,empty,colors))
assert(creates==2 and updates==2 and faces[1][1][2]==8 and faces[1][1][3]==7,
    'updated face exchanged world distance and height')
assert(r:submit(WORLD,second,empty,colors))
assert(updates==2,'unchanged references caused native triangle updates')
r:clear()
assert(destroys==2 and next(faces)==nil,'clear left retained faces behind')
r:release()
assert(gui_destroys==1,'world GUI not released')
''')

    def test_opposed_cordon_text_panels_keep_outward_single_winding_on_create_and_update(self):
        replay(GUI + '''
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local neg_outer={'cordon_text',{0,-1,0},{0,-1,1},{1,-1,0}}
local neg_inner={'cordon_text',{0,-1,0},{1,-1,0},{0,-1,1}}
local pos_outer={'cordon_text',{0,1,0},{1,1,0},{0,1,1}}
local pos_inner={'cordon_text',{0,1,0},{0,1,1},{1,1,0}}
local colors={cordon_text=sr.Color(255,255,255,255)}
local function normal_y(face)
    local a,b,c=face[1],face[2],face[3]
    -- Standard (b-a) x (c-a), Y component.
    return (b[3]-a[3])*(c[1]-a[1])-(b[1]-a[1])*(c[3]-a[3])
end
assert(r:submit(WORLD,{neg_outer,neg_inner,pos_outer,pos_inner},{},colors))
assert(creates==4 and r.count==4,'text faces were duplicated by reverse winding')
assert(normal_y(faces[1])<0 and normal_y(faces[2])>0
    and normal_y(faces[3])>0 and normal_y(faces[4])<0,
    'each of four panel faces must face outward after native conversion')
neg_outer={'cordon_text',{0,-1,0},{0,-1,1},{2,-1,0}}
neg_inner={'cordon_text',{0,-1,0},{2,-1,0},{0,-1,1}}
pos_outer={'cordon_text',{0,1,0},{2,1,0},{0,1,1}}
pos_inner={'cordon_text',{0,1,0},{0,1,1},{2,1,0}}
assert(r:submit(WORLD,{neg_outer,neg_inner,pos_outer,pos_inner},{},colors))
assert(updates==4 and creates==4,'single-winding text update changed encoding or duplicated faces')
assert(normal_y(faces[1])<0 and normal_y(faces[2])>0
    and normal_y(faces[3])>0 and normal_y(faces[4])<0,
    'updated text winding no longer faces outward')
''')

    def test_mixed_text_and_regular_face_slots_validate_and_retain_correctly(self):
        replay(GUI + '''
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local text_a={'cordon_text',{0,-1,0},{0,-1,1},{1,-1,0}}
local normal_a={'air',{2,0,0},{2,1,0},{3,0,0}}
local text_b={'cordon_text',{0,1,0},{1,1,0},{0,1,1}}
local normal_b={'air',{4,0,0},{4,1,0},{5,0,0}}
local colors={cordon_text=sr.Color(255,255,255,255),air=sr.Color(255,255,255,255)}
local batch={text_a,normal_a,text_b,normal_b}
assert(r:submit(WORLD,batch,{},colors))
assert(r.count==6 and creates==6,'mixed batches must allocate one text face and two ordinary faces')
assert(r:submit(WORLD,batch,{},colors) and updates==0,
    'retained mixed batches must not rescan incorrect pair slots')
local invalid={'air',{0,0,0},{0,0,0},{math.huge,0,0}}
local rejected,reason=r:submit(WORLD,{text_a,invalid,normal_b},{},colors)
assert(not rejected and reason=='invalid face/color' and creates==6 and updates==0,
    'validation must inspect the correct slot after a single-winding text face')
assert(r:submit(WORLD,batch,{},colors) and updates==0,
    'rejected mixed replacement must leave retained records intact')
''')

    def test_changed_flow_updates_only_changed_faces_and_handles_shifted_offsets(self):
        replay(GUI + '''
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local a={'air',{1,2,3},{4,2,3},{1,5,6}}
local b={'air',{11,12,13},{14,12,13},{11,15,16}}
local c={'air',{21,22,23},{24,22,23},{21,25,26}}
local colors={air=sr.Color(255,255,255,255)}
local static={a}
assert(r:submit(WORLD,static,{b},colors))
assert(r:submit(WORLD,static,{c},colors))
assert(updates==2,'unchanged static face was updated with the moving nameplates')
assert(faces[r.ids[3]][1][1]==21 and faces[r.ids[1]][1][1]==1)
assert(r:submit(WORLD,{}, {c},colors))
assert(updates==4 and destroys==2,'shrinking static batch left stale offset records')
assert(faces[r.ids[1]][1][1]==21)
assert(r:submit(WORLD,{c,a},{b},colors))
assert(r.count==6 and faces[r.ids[5]][1][1]==11,'growing/reordered batch retained wrong positions')
''')

    def test_all_guide_faces_match_world_geometry_on_creation_update_and_id_reuse(self):
        replay(GUI + THROW + '''
M.show_cordon=true;M.show_ground_border=true;M.solid_active=true
local function frames(n) for _=1,n do tick(1) end end
local function same(a,b)
    for j=1,3 do assert(math.abs(a[j]-b[j])<0.0001,
        'rendered face moved away from world geometry (distance/height swap)') end
end
local function check()
    local index=0
    local outward_text=0
    for _,batch in ipairs({M.seg,M.flow_seg}) do
        for _,s in ipairs(batch) do
            if s[4] then
                index=index+1
                local face=faces[M.solid_renderer.ids[index]]
                if s[1]=='cordon_text' then
                    -- Text is submitted once with reversed winding so the
                    -- authored panel face points outward.
                    same(face[1],s[2]);same(face[2],s[4]);same(face[3],s[3])
                    local first=next(M.impacts)
                    local imp=first and M.impacts[first]
                    assert(imp and imp.heading,'text fixture lacks confirmed impact heading')
                    local hx,hy=imp.heading[1],imp.heading[2]
                    local len=math.sqrt(hx*hx+hy*hy);hx,hy=hx/len,hy/len
                    local px,py=-hy,hx
                    local cx=(face[1][1]+face[2][1]+face[3][1])/3-imp.p[1]
                    local cy=(face[1][2]+face[2][2]+face[3][2])/3-imp.p[2]
                    local lateral=cx*px+cy*py
                    local abx,aby,abz=face[2][1]-face[1][1],face[2][2]-face[1][2],face[2][3]-face[1][3]
                    local acx,acy,acz=face[3][1]-face[1][1],face[3][2]-face[1][2],face[3][3]-face[1][3]
                    local nx=aby*acz-abz*acy
                    local ny=abz*acx-abx*acz
                    local facing=nx*px+ny*py
                    local expected=(math.abs(lateral)>10 and 1 or -1)*(lateral<0 and -1 or 1)
                    assert(facing*expected>0,
                        'real cordon panel text winding points into the plate instead of outward')
                    outward_text=outward_text+1
                else
                    same(face[1],s[2]);same(face[2],s[3]);same(face[3],s[4])
                    index=index+1
                    face=faces[M.solid_renderer.ids[index]]
                    same(face[1],s[2]);same(face[2],s[4]);same(face[3],s[3])
                end
            end
        end
    end
    assert(index>0,'fixture did not draw true-filled guides')
    assert(outward_text>0,'fixture did not produce real cordon text panels: '..#(M.cordon_seg or {}))
end
frames(1);check() -- first native creations
frames(44);check() -- cached terrain completion and repeated updates
for _,imp in pairs(M.impacts) do imp.p={13.7,109.1,14.5};imp.heading={0.6,0.8,0} end
frames(45);check() -- nonzero offset, oblique heading, terrain/cache rebuild and ID reuse
''')

    def test_real_guides_contain_faces_instead_of_scan_fill_and_keep_terrain_budget(self):
        replay(GUI + SCENE + '''
M.adapt_range=false;M.show_type=false -- preserve the generic geometry budget for renderer validation
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
assert(M.seg_count<1500,'filled borders and repeated names exceeded the generic geometry budget')
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
assert(M.solid_active and next(faces),'through-world must retain true fill')
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
