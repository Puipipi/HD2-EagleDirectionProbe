"""Three equally spaced nameplates per side form a stable looping conveyor."""
import unittest
from test_mission_feedback import replay
from test_solid_renderer import GUI
from test_type_display import FLAT, TYPES


PANELS = '''
local function panel_intervals(circle,side)
    local intervals={}
    for _,s in ipairs(M.flow_seg) do
        if s[1]=='cordon_dim' and s[2][2]*side>0 then
            local lo,hi=math.huge,-math.huge
            for k=2,s[4] and 4 or 3 do
                local p=s[k]
                local t=circle and math.atan2(p[1],math.abs(p[2]))*25 or p[1]
                lo,hi=math.min(lo,t),math.max(hi,t)
            end
            intervals[#intervals+1]={lo,hi}
        end
    end
    table.sort(intervals,function(a,b) return a[1]<b[1] end)
    local result={}
    for _,v in ipairs(intervals) do
        local last=result[#result]
        if last and v[1]<=last[2]+0.001 then last[2]=math.max(last[2],v[2])
        else result[#result+1]={v[1],v[2]} end
    end
    return result
end
'''


class CordonCycleTest(unittest.TestCase):
    def test_panels_refresh_at_ten_hz_while_arrows_keep_twenty_hz_and_speed(self):
        replay(GUI+TYPES+FLAT+PANELS+'''
frames(60)
local changed,old=0,nil
local sky_changed,old_sky=0,nil
for frame=1,140 do
    FAKE_TIME=220+frame/140;update()
    local first,sky
    for _,s in ipairs(M.flow_seg) do
        if s[1]=='cordon_dim' and not first then first=s end
        if s[1]=='sky1' and not sky then sky=s end
    end
    if old and old~=first then changed=changed+1 end
    if old_sky and old_sky~=sky then sky_changed=sky_changed+1 end
    old,old_sky=first,sky
end
assert(changed>=9 and changed<=11,'panels rebuilt more often than ten Hz')
assert(sky_changed>=19 and sky_changed<=21,'panel throttle changed arrow cadence')
local function centers()
    local intervals=panel_intervals(false,1)
    local out={}
    for _,p in ipairs(intervals) do out[#out+1]=(p[1]+p[2])/2 end
    return out,intervals
end
FAKE_TIME=240;update()
local before,intervals=centers()
FAKE_TIME=240.2;update()
local after=centers()
local panel_width=intervals[1][2]-intervals[1][1]
local period=(100/3-(-100/3))-panel_width
assert(#before==3 and #after==3,'all three panels must remain in the moving sample')
local used={}
for _,a in ipairs(before) do
    local match
    for i,b in ipairs(after) do
        local delta=(b-a+period/2)%period-period/2
        if not used[i] and math.abs(delta-2)<0.001 then match=i;break end
    end
    assert(match,'a panel stopped moving ten metres per second modulo its wrap period')
    used[match]=true
end
''')

    def test_three_per_side_keep_equal_spacing_and_labels_over_full_wraps(self):
        for renderer in ('', GUI):
            for kind,lo,hi in ((18,-100/3,100/3),(30,-5,55),(3,-25*3.141592653589793/2,25*3.141592653589793/2)):
                with self.subTest(solid=bool(renderer),kind=kind):
                    replay(renderer+TYPES+FLAT+PANELS+f'''
type_rows[1].type={kind}
frames(60)
local queries=casts
local circular={str(kind==3).lower()}
local expected_width
for frame=0,179 do
    FAKE_TIME=210+frame*0.05;update()
    local sides={{}}
    for _,side in ipairs({{-1,1}}) do
        local panels=panel_intervals(circular,side)
        sides[side]=panels
        assert(#panels==3,'loop did not retain exactly three panels per side')
        local width=panels[1][2]-panels[1][1]
        expected_width=expected_width or width
        assert(math.abs(width-expected_width)<0.001,'wrap changed panel size')
        local spacing=(({hi})-({lo})-width)/3
        for i,p in ipairs(panels) do
            assert(p[1]>={lo}-0.001 and p[2]<={hi}+0.001,'panel crossed corridor end')
            assert(math.abs(p[2]-p[1]-width)<0.001,'panel was clipped at wrap')
            if i>1 then
                assert(math.abs(p[1]-panels[i-1][1]-spacing)<0.001,'conveyor spacing became uneven')
            end
            local letters=0
            for _,s in ipairs(M.flow_seg) do if s[1]=='cordon_text' and s[2][2]*side>0 then
                local v=s[2]
                local t=circular and math.atan2(v[1],math.abs(v[2]))*25 or v[1]
                if t>=p[1] and t<=p[2] then letters=letters+1 end
            end end
            assert(letters>0,'looping panel lost its name')
        end
    end
    for i=1,3 do assert(math.abs(sides[-1][i][1]-sides[1][i][1])<0.001,
        'left and right panels do not share the same phase') end
end
assert(casts==queries and max_frame<=2,'three-panel conveyor added terrain queries')
''')


if __name__ == '__main__': unittest.main()
