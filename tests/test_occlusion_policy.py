"""Integration contract for the optional dashed x-ray outline channel."""
import unittest

from test_mission_feedback import replay, THROW
from test_solid_renderer import GUI
from test_departure_options_performance import MENU


class OcclusionPolicyTest(unittest.TestCase):
    def test_hiding_after_world_exit_does_not_touch_dead_primary_line(self):
        replay(GUI+'''
local probe=HD2EagleDirectionProbe
local guarded
for i=1,debug.getinfo(update,'u').nups do
    local name,value=debug.getupvalue(update,i)
    if name=='guarded' then guarded=value end
end
local draw
for i=1,debug.getinfo(guarded,'u').nups do
    local name,value=debug.getupvalue(guarded,i)
    if name=='draw_corridor' then draw=value end
end
assert(draw,'draw_corridor fixture unavailable')
local deadworld,line={},{}
probe.lines={[deadworld]=line};probe.line_order={deadworld}
probe.line,probe.line_world=line,deadworld
probe.impacts,probe.impact_order={},{}
probe.tracks,probe.track_order={},{}
sr.Application.worlds=function() return {} end
local before=#ADDED
draw()
assert(#ADDED==before,'hiding submitted/reset a line through an exited world')
assert(probe.line==nil and probe.line_world==nil,
    'dead primary line reference was not cleared')
assert(probe.lines[deadworld]==nil,'dead primary line remained in world cache')
''')

    def test_release_only_destroys_line_handles_from_live_worlds(self):
        replay(GUI+'''
local probe=HD2EagleDirectionProbe
local deadworld,liveworld={},WORLD
local deadline,deadxray={},{}
local destroyed={}
sr.Application.worlds=function() return {liveworld} end
sr.World.destroy_line_object=function(world,line)
    destroyed[#destroyed+1]={world=world,line=line}
end
probe.lines={[deadworld]=deadline};probe.line_order={deadworld}
probe.line,probe.line_world=deadline,deadworld
probe.xray_line,probe.xray_world=deadxray,deadworld
shutdown()
assert(#destroyed==0,'release called a destructor through a world absent from Application.worlds')

local primary,xray={},{}
probe.lines={[liveworld]=primary};probe.line_order={liveworld}
probe.line,probe.line_world=primary,liveworld
probe.xray_line,probe.xray_world=xray,liveworld
shutdown()
assert(#destroyed==2 and destroyed[1].world==liveworld and destroyed[2].world==liveworld,
    'live-world primary/xray line handles should both be destroyed')
''')

    def test_through_world_keeps_fill_and_adds_only_a_separate_line_channel(self):
        replay(GUI+THROW+'''
local probe=HD2EagleDirectionProbe
local guarded
for i=1,debug.getinfo(update,'u').nups do
    local name,value=debug.getupvalue(update,i)
    if name=='guarded' then guarded=value end
end
local draw
for i=1,debug.getinfo(guarded,'u').nups do
    local name,value=debug.getupvalue(guarded,i)
    if name=='draw_corridor' then draw=value end
end
assert(draw,'draw_corridor fixture unavailable')
local primary=probe.line
assert(primary and primary.flag==false,'primary line object must depth-test')
assert(probe.solid_active,'fixture should begin with solid fill enabled')
local created=#CREATED_LINE_OBJECTS
local submitted=#LINE_SUBMISSIONS
probe.through_world=true
probe.geom_key=nil;probe.need_submit=true
draw()
assert(probe.solid_active and probe.solid_triangles>0,
    'through-world mode must retain visible filled geometry: active='
        ..tostring(probe.solid_active)..' triangles='..tostring(probe.solid_triangles)
        ..' status='..tostring(probe.solid_status)..' failed='..tostring(probe.solid_failed)
        ..' fill='..tostring(probe.solid_fill)..' through='..tostring(probe.through_world)
        ..' renderer='..tostring(probe.solid_renderer)..' errors='..tostring(probe.errors)
        ..' draw_off='..tostring(probe.draw_off)..' occlusion='..tostring(probe.occlusion_status))
assert(#CREATED_LINE_OBJECTS==created+1,'x-ray should allocate one separate line object')
local xray=CREATED_LINE_OBJECTS[#CREATED_LINE_OBJECTS]
assert(xray.flag==true and xray~=primary,'secondary channel must disable depth testing')
assert(#LINE_SUBMISSIONS>=submitted+2,'primary and secondary channels were not both submitted')
local primary_count,xray_count=0,0
for i=submitted+1,#LINE_SUBMISSIONS do
    local record=LINE_SUBMISSIONS[i]
    if record.line==primary then primary_count=record.count end
    if record.line==xray then xray_count=record.count end
end
assert(primary_count>0 and xray_count>0,'both depth-tested and x-ray outlines need lines')
local primary_text,xray_text,plate_outline=false,false,false
for _,batch in ipairs({probe.seg,probe.flow_seg}) do
    for _,s in ipairs(batch) do if s[1]=='cordon_text' then primary_text=true end end
end
for _,outline in ipairs({probe.occlusion_static_cache,probe.occlusion_flow_cache}) do
    for _,s in ipairs(outline.dashed) do
        if s[1]=='cordon_text' then xray_text=true end
        if s[1]=='cordon' or s[1]=='cordon_dim' then plate_outline=true end
    end
end
assert(primary_text,'fixture must retain the normal filled/primary text geometry')
assert(not xray_text,'x-ray contour should omit glyph strokes while retaining plate outline')
assert(plate_outline,'x-ray outline removed the plate body contour along with text')
local static_outline_count=#probe.occlusion_static_cache.primary
local static_dash_count=#probe.occlusion_static_cache.dashed
local last_xray_count=xray_count
for _=1,60 do
    draw()
    assert(#probe.occlusion_static_cache.primary==static_outline_count
        and #probe.occlusion_static_cache.dashed==static_dash_count,
        'stable frames mutated cached static outlines')
    last_xray_count=0
    for i=#LINE_SUBMISSIONS,1,-1 do
        local record=LINE_SUBMISSIONS[i]
        if record.line==xray then last_xray_count=record.count;break end
    end
    assert(last_xray_count==xray_count,'stable frames duplicated outline segments')
end
local xray_draws=#LINE_SUBMISSIONS
probe.through_world=false
probe.geom_key=nil;probe.need_submit=true
draw()
assert(xray.destroyed,'turning off through-world must release the x-ray object')
for i=xray_draws+1,#LINE_SUBMISSIONS do
    assert(LINE_SUBMISSIONS[i].line~=xray,'disabled x-ray channel dispatched stale geometry')
end
assert(probe.solid_active and probe.solid_triangles>0,
    'turning through-world off must preserve visible fill')
''')

    def test_scan_fill_fallback_stays_in_primary_and_is_filtered_from_xray(self):
        replay(THROW+MENU+'''
local probe=HD2EagleDirectionProbe
local guarded
for i=1,debug.getinfo(update,'u').nups do
    local name,value=debug.getupvalue(update,i)
    if name=='guarded' then guarded=value end
end
local draw
for i=1,debug.getinfo(guarded,'u').nups do
    local name,value=debug.getupvalue(guarded,i)
    if name=='draw_corridor' then draw=value end
end
tick(25) -- cross menu cadence and register the real saved option callback
apply('solid_fill',false);tick(1)
assert(not probe.solid_active,'fallback fixture unexpectedly has retained fill')
local ground_off=probe.ground_seg
for _,s in ipairs(ground_off) do
    assert(not s.scan_fill and not s.outline_boundary,'OFF generated xray metadata')
end
apply('through_world',true);tick(1)
assert(probe.ground_seg~=ground_off,'through mode reused stale ground fallback geometry')
draw()
assert(not probe.solid_active and probe.line.flag==false and M.xray_line.flag==true,
    'fallback should still use separate depth-tested and x-ray line objects')
local scans,all_lines=0,0
for _,batch in ipairs({probe.seg,probe.flow_seg}) do
    for _,s in ipairs(batch) do
        if s.scan_fill then scans=scans+1 end
        if not s[4] then all_lines=all_lines+1 end
    end
end
assert(scans>0,'fixture must exercise scan-line fill fallback')
local outline=require('mods/codex/eagle_occlusion_outline')
local expected,unfiltered=0,0
for _,batch in ipairs({probe.seg,probe.flow_seg}) do
    local filtered={}
    for _,s in ipairs(batch) do
        if not s.scan_fill and s[1]~='cordon_text' then filtered[#filtered+1]=s end
    end
    expected=expected+#outline.dash(outline.build(filtered),1.2,0.8)
    unfiltered=unfiltered+#outline.dash(outline.build(batch),1.2,0.8)
end
local xray_count=0
for i=#LINE_SUBMISSIONS,1,-1 do
    if LINE_SUBMISSIONS[i].line==M.xray_line then xray_count=LINE_SUBMISSIONS[i].count;break end
end
assert(xray_count==expected and expected<unfiltered and scans>0,
    'x-ray included internal scan fill rows: xray='..xray_count..' expected='..expected
        ..' unfiltered='..unfiltered)
assert(FRAME_HAS_LINES,'primary fallback lost visible scan fill')
''')


if __name__ == '__main__':
    unittest.main()
