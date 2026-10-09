"""Light-panel positions move with the existing cached direction animation."""
import unittest

from test_mission_feedback import replay
from test_terrain_query import SCENE


class CordonMotionTest(unittest.TestCase):
    def test_panels_and_their_labels_move_at_ten_metres_per_second_on_cached_terrain(self):
        replay(SCENE + '''
M.adapt_range=false;M.show_type=false
frames(45)
FAKE_TIME=201
frames(1)
local function first(kind)
    for _,s in ipairs(M.flow_seg or {}) do
        if s[1]==kind then return s[2][1] end
    end
end
local x,label=first('cordon'),first('cordon_text')
assert(x and label,'light panels/attached letters must be in the motion cache')
local static,builds,oldcasts=M.ground_seg,M.ground_builds,casts
frames(6) -- 0.30 s: three whole panel-cache periods, independent of starting phase.
assert(math.abs(first('cordon')-x-3)<0.05,'light panel positions did not advance at 10 m/s')
assert(math.abs(first('cordon_text')-label-3)<0.05,'lettering detached from its moving panel')
assert(M.ground_seg==static and M.ground_builds==builds and casts==oldcasts,
    'panel motion rebuilt the static ground or queried terrain again')
''')

    def test_panels_animate_when_ground_triangles_and_sky_are_off_and_reuse_same_bucket(self):
        replay(SCENE + '''
M.adapt_range=false;M.show_type=false
M.show_ground_triangles=false;M.show_sky=false
frames(45)
local before=M.flow_seg
assert(before and #before>0,'border-only mode lost moving light panels')
local x=before[1][2][1]
FAKE_TIME=FAKE_TIME+0.001;update()
assert(M.flow_seg==before,'light panels rebuilt inside the same 20 Hz bucket')
frames(5)
assert(M.flow_seg~=before and M.flow_seg[1][2][1]~=x,'border-only panels remained static')
M.show_cordon=false;frames(1)
assert(#M.flow_seg==0,'disabled cordon kept its own animation alive')
''')

    def test_cycle_stays_inside_the_corridor_with_persistent_repeated_names(self):
        replay(SCENE.replace("return math.max(0, 30 - math.abs(x - 60)), 'HIT'",
                             "return 0, 'HIT'") + '''
M.adapt_range=false;M.show_type=false
frames(45)
for i=0,59 do
    FAKE_TIME=210+i*0.05;update()
    local labels,panels=0,0
    for _,s in ipairs(M.flow_seg or {}) do
        if s[1]=='cordon_text' then
            labels=labels+1
            for k=2,3 do assert(math.abs(s[k][1])<=100,'name left the sampled corridor') end
        elseif s[1]=='cordon' or s[1]=='cordon_dim' then
            panels=panels+1
            for k=2,3 do assert(math.abs(s[k][1])<=100,'moving panel left sampled corridor') end
        end
    end
    local font=require('mods/codex/eagle_cordon_font')
    local text=M.show_type and M.type_profiles.catalog[18].panel_label or 'EAGLE ?'
    local strokes=0
    for i=1,#text do
        local glyph=font.get(text:sub(i,i))
        if glyph then strokes=strokes+#glyph end
    end
    assert(labels==6*strokes and panels>0,
        'moving names must remain complete on all six panels: labels='..labels..' expected='..(6*strokes))
    -- With names hidden, the readable generic vector label adds 42 lines on
    -- this type-18 scene (186 versus 144 in the rc11 replay), with the original
    -- 27-line headroom retained for this motion fixture.
    assert(M.seg_count<=1250+42,
        'moving-panel cycle exceeded the measured vector-font line budget: '..M.seg_count)
end
''')


if __name__=='__main__':
    unittest.main()
