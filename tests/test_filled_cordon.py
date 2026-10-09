"""Filled borders and persistent, equal-size moving hologram nameplates."""
import unittest
from test_mission_feedback import replay
from test_solid_renderer import GUI
from test_type_display import FLAT, TYPES


class FilledCordonTest(unittest.TestCase):
    def test_border_covers_a_band_instead_of_three_parallel_lines(self):
        replay(GUI+FLAT+'''
M.adapt_range=false;M.show_type=false
frames(50)
local area,n=0,0
for _,s in ipairs(M.seg) do if s[1]=='ground' then
    assert(s[4],'true-fill border still contains line strands')
    local a,b,c=s[2],s[3],s[4]
    area=area+math.abs((b[1]-a[1])*(c[2]-a[2])-(b[2]-a[2])*(c[1]-a[1]))/2
    n=n+1
end end
assert(n>0 and math.abs(area-212)<0.01,'white perimeter has gaps or wrong filled width')
assert(max_frame<=2 and casts<=85,'filled border increased terrain calls')
''')

    def test_every_moving_panel_keeps_its_name_and_same_size_through_handoff(self):
        replay(GUI+FLAT+'''
M.adapt_range=false;M.show_type=false
frames(50)
for frame=0,119 do
    FAKE_TIME=210+frame*0.05;update()
    local intervals={}
    for _,s in ipairs(M.flow_seg) do
        if s[1]=='cordon_dim' and s[2][2]<0 then
            local lo,hi=math.huge,-math.huge
            for k=2,#s do lo=math.min(lo,s[k][1]);hi=math.max(hi,s[k][1]) end
            intervals[#intervals+1]={lo,hi}
        end
    end
    table.sort(intervals,function(a,b) return a[1]<b[1] end)
    local panels={}
    for _,r in ipairs(intervals) do
        local p=panels[#panels]
        if p and r[1]<=p[2]+0.001 then p[2]=math.max(p[2],r[2])
        else panels[#panels+1]={r[1],r[2]} end
    end
    assert(#panels==3,'opaque conveyor must keep three complete plates per side')
    local width=panels[1][2]-panels[1][1]
    for _,p in ipairs(panels) do
        assert(math.abs(p[2]-p[1]-width)<0.001,'label handoff changed a panel length')
        local letters=0
        for _,s in ipairs(M.flow_seg) do
            if s[1]=='cordon_text' and s[2][2]<0 and s[2][1]>=p[1] and s[2][1]<=p[2] then
                letters=letters+1
                assert(s[4],'name still relies on thin native line strokes')
                assert(math.abs(math.abs(s[2][2])-6)>0.01,'letters are coplanar with panel wash')
            end
        end
        assert(letters>0,'a distant/outer moving panel has no persistent name')
    end
end
assert(max_frame<=2 and casts<=85,'panel cycle queried uncached terrain')
''')

    def test_circular_filled_border_and_panels_stay_on_cached_terrain(self):
        replay(GUI+TYPES+FLAT+'''
type_rows[1].type=3
frames(60)
local n,area=0,0
for _,s in ipairs(M.seg) do if s[1]=='ground' then
    assert(s[4],'circular border is still line-only')
    n=n+1
    local a,b,c=s[2],s[3],s[4]
    area=area+math.abs((b[1]-a[1])*(c[2]-a[2])-(b[2]-a[2])*(c[1]-a[1]))/2
    for k=2,4 do assert(math.abs(s[k][3]-0.08)<0.001,'border left cached surface') end
end end
assert(n>=96 and area>78 and area<79,'annulus lost its filled area')
assert(max_frame<=2 and casts<=85)
''')


if __name__=='__main__': unittest.main()
