"""Sky arrows share type-specific bounds, motion and saved adaptation controls."""
import unittest
from test_mission_feedback import replay
from test_type_display import TYPES, FLAT
from test_departure_options_performance import MENU
from test_solid_renderer import GUI


class SkyAdaptiveTest(unittest.TestCase):
    def test_all_types_keep_complete_arrows_inside_reference_bounds_over_wraps(self):
        for kind,lo,hi in ((18,-100/3,100/3),(30,-5,55),(65,-100/3,100/3),
                           (133,-100/3,100/3),(38,-100/3,100/3),
                           (126,-100/3,100/3),(3,-25,25),(140,-100,100)):
            with self.subTest(kind=kind):
                replay(GUI+TYPES+FLAT+f'''
type_rows[1].type={kind};frames(60)
M.impacts[1].p={{17,29,5}};M.impacts[1].heading={{0.6,0.8,0}}
M.tracks.design.heading={{0.6,0.8,0}};frames(45)
local queries=casts
local function check(lo,hi)
    local n=0
    for _,s in ipairs(M.flow_seg) do if s[1]:match('^sky%d$') then
        n=n+1
        for k=2,4 do
            local p=s[k]
            local along=(p[1]-17)*0.6+(p[2]-29)*0.8
            local lateral=-(p[1]-17)*0.8+(p[2]-29)*0.6
            assert(along>=lo-0.001 and along<=hi+0.001,'sky arrows ignored adaptive corridor ends')
            assert(math.abs(lateral)<0.001,'sky arrows lost incoming direction')
        end
    end end
    assert(n>0,'adaptive sky arrows disappeared')
end
for i=1,150 do frames(1);check({lo},{hi}) end
assert(casts==queries and max_frame<=2,'adaptive sky arrows added raycasts')
''')

    def test_saved_adaptation_toggle_changes_sky_span_without_changing_arrow_shape(self):
        replay(GUI+TYPES+FLAT+MENU+'''
type_rows[1].type=30;frames(60)
local function span()
    local lo,hi=math.huge,-math.huge
    local glyph_lo,glyph_hi=math.huge,-math.huge
    for _,s in ipairs(M.flow_seg) do if s[1]:match('^sky%d$') then
        for k=2,4 do
            lo,hi=math.min(lo,s[k][1]),math.max(hi,s[k][1])
            if s[1]=='sky1' then glyph_lo,glyph_hi=math.min(glyph_lo,s[k][1]),math.max(glyph_hi,s[k][1]) end
        end
    end end
    assert(math.abs(glyph_hi-glyph_lo-14)<0.001,'adaptation stretched upright glyph')
    return hi-lo
end
assert(span()<=60)
apply('adapt_range',false);frames(45)
assert(span()>140,'range-off did not restore generic sky span')
apply('adapt_range',true);frames(45)
assert(span()<=60,'range-on did not restore short strafe sky span')
''')


if __name__ == '__main__': unittest.main()
