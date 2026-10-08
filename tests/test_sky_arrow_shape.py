"""Sky glyphs must read as an upright right arrow with a shaft, not a flat triangle."""
import unittest

from test_mission_feedback import replay
from test_terrain_query import SCENE


class SkyArrowShapeTest(unittest.TestCase):
    def test_upright_arrow_has_a_filled_shaft_and_head_aligned_to_each_heading(self):
        for hx, hy in ((1, 0), (0, 1), (0.6, 0.8)):
            with self.subTest(heading=(hx, hy)):
                replay(SCENE + f'''
M.impacts[1].heading={{{hx},{hy},0}}
M.tracks.design.heading={{{hx},{hy},0}}
frames(45)
local hx,hy={hx},{hy}
local points,lo,hi={{}},math.huge,-math.huge
local glyph={{}}
for _,s in ipairs(M.flow_seg) do
    if s[1]=='sky1' then
        glyph[#glyph+1]=s
        for k=2,3 do
            local p=s[k]
            local along=p[1]*hx+p[2]*hy
            assert(math.abs(-p[1]*hy+p[2]*hx)<0.001,'sky arrow is not in one vertical plane')
            lo,hi=math.min(lo,along),math.max(hi,along)
            points[#points+1]={{along,p[3]}}
        end
    end
end
assert(hi-lo>12 and hi-lo<16,'right arrow needs a shaft beyond its head')
local bottom,top=math.huge,-math.huge
for _,p in ipairs(points) do bottom,top=math.min(bottom,p[2]),math.max(top,p[2]) end
assert(top-bottom>6 and top-bottom<6.5,'arrow head must open vertically')
local center=(bottom+top)/2
local shaft,tip,wide_head=0,false,false
for _,s in ipairs(glyph) do
    local a,b=s[2],s[3]
    local ta,tb=a[1]*hx+a[2]*hy,b[1]*hx+b[2]*hy
    if math.abs(ta-lo)<0.001 and tb>lo+7 and tb<hi-3
        and math.abs(a[3]-center)<0.7 and math.abs(b[3]-center)<0.7 then shaft=shaft+1 end
    for _,p in ipairs({{a,b}}) do
        local t=p[1]*hx+p[2]*hy
        if math.abs(t-hi)<0.001 and math.abs(p[3]-center)<0.001 then tip=true end
        if t>lo+7 and t<hi-3 and math.abs(p[3]-center)>3 then wide_head=true end
    end
end
assert(shaft>=8,'sky right arrow has no filled rectangular shaft')
assert(tip and wide_head,'sky arrow lacks an upright pointed head')
''')


if __name__ == '__main__':
    unittest.main()
