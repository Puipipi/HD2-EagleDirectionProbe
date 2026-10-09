"""Ground cues stay close to cached surfaces; warning plates are opaque."""
import unittest
from test_mission_feedback import replay
from test_solid_renderer import GUI
from test_type_display import FLAT, TYPES


class GroundContactTest(unittest.TestCase):
    def test_flat_ground_borders_and_triangles_have_small_clearance_in_both_modes(self):
        for renderer in ('', GUI):
            with self.subTest(solid=bool(renderer)):
                replay(renderer+FLAT+'''
frames(50)
local border,arrow=0,0
for _,batch in ipairs({M.seg,M.flow_seg}) do
    for _,s in ipairs(batch) do
        if s[1]=='ground' or s[1]=='flow' then
            if s[1]=='ground' then border=border+1 else arrow=arrow+1 end
            for k=2,s[4] and 4 or 3 do
                assert(s[k][3]>=0.03 and s[k][3]<=0.1,
                    'ground cue floats visibly above a flat cached surface')
            end
        end
    end
end
assert(border>0 and arrow>0,'contact check missed an entire cue')
assert(max_frame<=2 and casts<=85,'closer ground cues increased collision budget')
''')

    def test_sloped_cached_surface_keeps_same_small_clearance_without_new_queries(self):
        for renderer in ('', GUI):
            with self.subTest(solid=bool(renderer)):
                replay(renderer+FLAT.replace("return 0, 'HIT'",
                    "return 0.2*x+0.1*y, 'HIT'")+'''
M.adapt_range=false
frames(50)
local near,far=0,0
for _,batch in ipairs({M.seg,M.flow_seg}) do
    for _,s in ipairs(batch) do
        if s[1]=='ground' or s[1]=='flow' then
            for k=2,s[4] and 4 or 3 do
                local p=s[k]
                local clearance=p[3]-(0.2*p[1]+0.1*p[2])
                assert(clearance>=0.03 and clearance<=0.1,
                    'ground cue lost slope fitting or retained the old hover offset')
                if math.abs(p[1])>60 then far=far+1 else near=near+1 end
            end
        end
    end
end
assert(near>0 and far>0,'slope check omitted near or distant terrain')
local previous=casts
frames(20)
assert(casts==previous and max_frame<=2,'contact adjustment added animation raycasts')
''')

    def test_plate_background_rim_and_letters_use_opaque_colours(self):
        replay(GUI+FLAT+'''
frames(50)
local background,rim,letters=false,false,false
for _,c in ipairs(COLORS) do
    if c.r==68 and c.g==8 and c.b==16 then
        assert(c.a==255,'warning plate background is translucent');background=true
    elseif c.r==255 and c.g==55 and c.b==65 then
        assert(c.a==255,'warning rim is translucent');rim=true
    elseif c.r==255 and c.g==225 and c.b==215 then
        assert(c.a==255,'warning letters are translucent');letters=true
    end
end
assert(background and rim and letters,'opaque plate colours were not submitted')
''')

    def test_opaque_plates_have_one_selected_lettering_copy(self):
        for circular in (False, True):
            with self.subTest(circular=circular):
                replay(GUI+TYPES+FLAT+('type_rows[1].type=3\n' if circular else
                    'M.adapt_range=false\n')+'''
frames(60)
local outside,inside=0,0
local circle=M.impacts[1].stratagem_type==3
for index,s in ipairs(M.flow_seg) do
    if s[1]=='cordon_text' then
        local p=s[2]
        local depth=circle and math.sqrt(p[1]^2+p[2]^2)-25 or math.abs(p[2])-6
        if depth>0.03 then outside=outside+1 end
        if depth< -0.03 then inside=inside+1 end
        assert(math.abs(math.abs(depth)-0.04)<0.001,
            'letter face overlaps opaque plate instead of sitting on its surface')
    end
end
assert(outside==0 or inside==0,
    'each opaque plate must submit only the viewer-selected lettering side')
assert(outside+inside>0,'selected lettering side was not submitted')
if circle then
    for _,s in ipairs(M.flow_seg) do if s[1]=='cordon_text' then
        for k=2,4 do
            local p=s[k]
            local r=math.sqrt(p[1]^2+p[2]^2)
            if r<25 then
                local dx,dy=p[1]/r,p[2]/r
                for _,q in ipairs(M.flow_seg) do if q[1]=='cordon_dim' then
                    local a,b=q[2],q[3]
                    local vx,vy=b[1]-a[1],b[2]-a[2]
                    local den=dx*vy-dy*vx
                    if math.abs(den)>1e-6 then
                        local hit=(a[1]*vy-a[2]*vx)/den
                        local t=(a[1]*dy-a[2]*dx)/den
                        assert(not (t>0 and t<1 and hit>0 and hit<r-0.001),
                            'inside text lies behind opaque circular plate chord')
                    end
                end end
            end
        end
    end end
end
assert(max_frame<=2,'two-sided text added native terrain queries')
''')


if __name__=='__main__': unittest.main()
