"""Thick continuous borders, upright red tape, larger/faster direction cues."""
import unittest

from test_mission_feedback import replay
from test_terrain_query import SCENE
from test_departure_options_performance import MENU


class CordonFeedbackTest(unittest.TestCase):
    def test_white_long_borders_are_thicker_and_unbroken_on_cached_flat_ground(self):
        replay(SCENE.replace("return math.max(0, 30 - math.abs(x - 60)), 'HIT'",
                             "return 0, 'HIT'") + '''
frames(45)
local lanes={}
for _,s in ipairs(M.seg) do
    if s[1]=='ground' and math.abs(s[2][2]-s[3][2])<0.001 then
        local y=s[2][2]
        lanes[y]=lanes[y] or {}
        lanes[y][#lanes[y]+1]={math.min(s[2][1],s[3][1]),math.max(s[2][1],s[3][1])}
    end
end
for _,side in ipairs({-1,1}) do
    local n,lo,hi=0,math.huge,-math.huge
    for y,segments in pairs(lanes) do
        if y*side>0 then
            n=n+1; lo=math.min(lo,y); hi=math.max(hi,y)
            table.sort(segments,function(a,b) return a[1]<b[1] end)
            assert(math.abs(segments[1][1]+100)<0.01,'border did not start at strip end')
            local finish=segments[1][2]
            for i=2,#segments do
                assert(math.abs(segments[i][1]-finish)<0.01,'solid border has a gap')
                finish=segments[i][2]
            end
            assert(math.abs(finish-100)<0.01,'border stopped short')
        end
    end
    assert(n>=3 and hi-lo>=0.49,'white border was not thickened on both long edges')
end
''')

    def test_red_tape_is_upright_on_long_edges_only_and_follows_the_distant_ridge(self):
        replay(SCENE + '''
frames(45)
local sides,levels={},{}
local count,raised=0,false
for _,s in ipairs(M.flow_seg) do
    if s[1]=='cordon' or s[1]=='cordon_dim' then
        count=count+1
        assert(math.abs(s[2][2]-s[3][2])<0.001,'red panel crossed a short edge')
        for k=2,3 do
            local p=s[k]
            assert(math.abs(math.abs(p[2])-6.015)<0.016,'tape left the upright boundary plane')
            sides[p[2]<0 and -1 or 1]=true
            local surface=math.max(0,30-math.abs(p[1]-60))
            local lift=p[3]-surface
            assert(lift>=1.09 and lift<=2.46,'warning panel ignored cached terrain or became a wall')
            levels[math.floor(lift*100+0.5)]=true
            if p[1]>50 and p[1]<70 and p[3]>20 then raised=true end
        end
    end
end
assert(count>50 and count<=160 and sides[-1] and sides[1],'bounded red panels on both sides are missing')
local n=0; for _ in pairs(levels) do n=n+1 end
assert(n>=3 and raised,'warning tape has no vertical area or distant terrain fitting')
local red=false
for _,c in ipairs(COLORS) do
    if c.r==255 and c.g<100 and c.b<110 and c.a>40 then red=true end
end
assert(red,'red geometry used a non-red native colour')
local static,old=M.seg,casts
frames(10)
assert(M.seg==static and casts==old,'red strips rebuilt or queried terrain for animation')
''')

    def test_cordon_is_separate_cut_corner_panels_with_clear_gaps(self):
        replay(SCENE.replace("return math.max(0, 30 - math.abs(x - 60)), 'HIT'",
                             "return 0, 'HIT'") + '''
frames(45)
FAKE_TIME=210;update()
local centers={}
local spacing=200/3
local phase=2100%spacing
for _,s in ipairs(M.flow_seg) do
    if s[1]=='cordon' or s[1]=='cordon_dim' then
        local x0,x1=math.min(s[2][1],s[3][1]),math.max(s[2][1],s[3][1])
        local center=math.floor(((x0+x1)/2-phase)/spacing+0.5)*spacing+phase
        assert(center>=-100 and center<=100,'warning panel exceeded corridor ends')
        assert(x0>=center-3.61 and x1<=center+3.61,'light panel bridged an intended gap')
        local dx,dz=math.abs(s[2][1]-s[3][1]),math.abs(s[2][3]-s[3][3])
        assert(dx<0.001 or dz<0.001 or (dx<=0.281 and dz<=0.201),'long cross-hatched wire fence survived redesign')
        centers[center]=true
    end
end
local n=0;for _ in pairs(centers) do n=n+1 end
assert(n>=2 and n<=3,'two or three spaced nameplates per long side required')
assert(M.seg_count<=1250,'panel redesign exceeded per-strike geometry budget')
''')

    def test_warning_tape_has_a_saved_switch_and_follows_the_border_switch(self):
        replay(SCENE + MENU + '''
saved['eagle_direction_probe.show_cordon']=false
frames(45)
local row=rows['eagle_direction_probe.show_cordon']
assert(row and row.default==true and M.show_cordon==false,'warning strip option/save missing')
assert(count('cordon')==0 and count('cordon_text')==0 and count('ground')>0,
    'saved disabled tape hid the white border or left its label')
apply('show_cordon',true);frames(1)
assert(count('cordon')>0 and count('cordon_text')>0 and count('ground')>0,
    'warning strip/label failed to return')
apply('show_ground_border',false);frames(1)
assert(count('cordon')==0 and count('cordon_dim')==0 and count('ground')==0,
    'warning tape ignored disabled ground borders')
assert(count('flow')>0 and count('sky1')>0,'border switch removed independent arrows')
''')

    def test_triangles_are_larger_and_ground_and_sky_move_together_at_ten_metres_per_second(self):
        replay(SCENE + '''
frames(45)
FAKE_TIME=200
frames(1)
local lo,hi,ylo,yhi=math.huge,-math.huge,math.huge,-math.huge
local x,sky
for _,s in ipairs(M.flow_seg) do
    if s[1]=='flow' then
        x=x or s[2][1]
        -- Inspect the first arrow without combining neighbouring glyphs.
        if s[2][1]<-70 and s[3][1]<-70 then
            for k=2,3 do
                lo,hi=math.min(lo,s[k][1]),math.max(hi,s[k][1])
                ylo,yhi=math.min(ylo,s[k][2]),math.max(yhi,s[k][2])
            end
        end
    elseif s[1]=='sky1' then sky=sky or s[2][1] end
end
assert(hi-lo>=5.19 and yhi-ylo>=5.79,'ground triangles did not grow by about thirty percent')
frames(5)
local newx,newsky
for _,s in ipairs(M.flow_seg) do
    if s[1]=='flow' then newx=newx or s[2][1]
    elseif s[1]=='sky1' then newsky=newsky or s[2][1] end
end
assert(math.abs(newx-x-2.5)<0.05 and math.abs(newsky-sky-2.5)<0.05,
    'ground and sky arrows must advance together at 10 m/s')
assert(M.seg_count<=1250,'warning tape/text exceeded the single-strike geometry budget')
''')

    def test_warning_text_is_upright_on_both_sides_without_a_gui_api(self):
        replay(SCENE.replace("return math.max(0, 30 - math.abs(x - 60)), 'HIT'",
                             "return 0, 'HIT'") + '''
frames(45)
FAKE_TIME=210;update()
local n,sides,low,high=0,{},math.huge,-math.huge
for _,s in ipairs(M.flow_seg) do
    if s[1]=='cordon_text' then
        n=n+1
        for k=2,3 do
            local p=s[k]
            assert(math.abs(math.abs(p[2])-6.04)<0.001,'label lost its offset from the upright boundary plane')
            assert(math.abs(p[1])<=100,'label should travel within the footprint')
            sides[p[2]<0 and -1 or 1]=true
            low,high=math.min(low,p[3]),math.max(high,p[3])
        end
    end
end
assert(n>=80 and n<=160 and sides[-1] and sides[1],'repeated world-space warning labels missing')
assert(high-low>=0.79 and low>1 and high<2.3,'warning lettering is not upright/readable on the tape')
assert(next(sr.Gui)==nil,'warning text must not invent a native GUI API')
local before=M.seg
frames(10)
assert(M.seg==before,'moving letters rebuilt the static ground')
''')


if __name__=='__main__':
    unittest.main()
