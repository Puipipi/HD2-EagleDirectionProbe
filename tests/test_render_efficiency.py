"""Opposed faces share frame-local vertices; retained-only frames skip colour work."""
import unittest
from test_mission_feedback import replay
from test_solid_renderer import GUI
from test_type_display import FLAT


class RenderEfficiencyTest(unittest.TestCase):
    def test_reverse_faces_share_frame_local_native_vertices(self):
        replay(GUI+'''
local count=0
local vector=sr.Vector3
sr.Vector3=function(...) count=count+1;return vector(...) end
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local a,b,c,d={1,2,3},{4,2,3},{4,5,3},{1,5,3}
local batch={{'air',a,b,c},{'air',a,c,d}}
local colors={air=sr.Color(255,255,255,255)}
assert(r:submit(WORLD,batch,{},colors))
assert(count==6,'a filled quad created duplicate native vertices for opposite windings')
count=0
a,b,c,d={11,12,13},{14,12,13},{14,15,13},{11,15,13}
assert(r:submit(WORLD,{{'air',a,b,c},{'air',a,c,d}},{},colors))
assert(count==6,'updated quad did not share frame-local converted vertices')
assert(faces[r.ids[1]][1][2]==12 and faces[r.ids[1]][1][3]==13,
    'vertex reuse regressed the update axis correction')
''')

    def test_retained_only_frames_do_not_rebuild_native_colours_at_render_fps(self):
        replay(GUI+FLAT+'''
frames(50)
local count=0
local color=sr.Color
sr.Color=function(...) count=count+1;return color(...) end
local q=casts
for i=1,140 do FAKE_TIME=FAKE_TIME+1/140;update() end
assert(count<=14*22,'native colours were recreated on unchanged retained-only frames')
assert(casts==q and max_frame<=2,'render optimization added terrain queries')
''')


    def test_mixed_created_and_updated_faces_keep_coordinates_and_frame_lifetimes(self):
        replay(GUI+'''
local epoch=1
local vector,create,change=sr.Vector3,sr.Gui.triangle,sr.Gui.update_triangle
sr.Vector3=function(...)
    local v=vector(...);v.epoch=epoch;return v
end
local function current(a,b,c)
    assert(a.epoch==epoch and b.epoch==epoch and c.epoch==epoch,
        'native vertex survived across submit frames')
end
sr.Gui.triangle=function(gui,a,b,c,...)
    current(a,b,c);return create(gui,a,b,c,...)
end
sr.Gui.update_triangle=function(gui,id,a,b,c,...)
    current(a,b,c);return change(gui,id,a,b,c,...)
end
local r=assert(require('mods/codex/eagle_solid_renderer').new(sr))
local a,b,c={11,22,33},{44,55,66},{77,88,99}
local colors={air=sr.Color(255,255,255,255)}
assert(r:submit(WORLD,{{'air',a,b,c}},{},colors))
epoch=2
-- Shared source points now enter both updated IDs and new IDs in one submit.
assert(r:submit(WORLD,{{'air',a,b,c},{'air',a,b,c}},{},colors))
assert(updates==2 and creates==4)
for i=1,4 do
    local p=faces[r.ids[i]][1]
    assert(p[1]==11 and p[2]==22 and p[3]==33,
        'mixed creation/update used the wrong native coordinate encoding')
end
epoch=3
assert(r:submit(WORLD,{{'air',a,b,c},{'air',a,b,c}},{},colors))
assert(updates==6,'new immutable records did not refresh native vertices')
''')


if __name__=='__main__': unittest.main()
