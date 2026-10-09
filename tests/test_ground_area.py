"""Reference-area overlay uses retained terrain-fitted faces, never new raycasts."""
import unittest
from test_mission_feedback import replay
from test_solid_renderer import GUI
from test_type_display import FLAT, TYPES
from test_departure_options_performance import MENU


AREA = '''
local function area_faces()
    local result={}
    for _,s in ipairs(M.seg or {}) do
        if s[1]=='area' then
            assert(s[4],'red area fell back to expensive scan lines')
            result[#result+1]=s
        end
    end
    return result
end
local function projected_area(batch)
    local total=0
    for _,s in ipairs(batch) do
        local a,b,c=s[2],s[3],s[4]
        local area=math.abs((b[1]-a[1])*(c[2]-a[2])-(c[1]-a[1])*(b[2]-a[2]))/2
        assert(area>0.0001,'degenerate area face')
        total=total+area
    end
    return total
end
'''


class GroundAreaTest(unittest.TestCase):
    def test_rectangle_covers_reference_bounds_and_fits_slope_without_extra_queries(self):
        replay(GUI+TYPES+FLAT.replace("return 0, 'HIT'", "return 0.2*x+0.1*y, 'HIT'")+MENU+AREA+'''
frames(60)
assert(#area_faces()==0,'new optional fill changed the default workload')
local queries=casts
apply('show_ground_area',true);frames(1)
local batch=area_faces()
assert(#batch>0 and #batch<=80,'rectangle overlay missing or needlessly dense')
assert(math.abs(projected_area(batch)-2400)<0.001,'airstrike reference has gaps or overlaps')
for _,s in ipairs(batch) do for k=2,4 do
    local p=s[k]
    assert(p[1]>=-60 and p[1]<=60 and math.abs(p[2])<=10,'fill escaped reference bounds')
    assert(math.abs(p[3]-(0.2*p[1]+0.1*p[2])-0.06)<0.0001,'fill floats above cached slope')
end end
assert(casts==queries and max_frame<=2,'area option increased collision work')
local red=false
for _,c in ipairs(COLORS) do
    if c.r==255 and c.g==32 and c.b==40 then
        assert(c.a>0 and c.a<=50,'red area blocks the ground');red=true
    end
end
assert(red,'red translucent colour was not submitted')
apply('ground_lift_cm',35);frames(1)
for _,s in ipairs(area_faces()) do for k=2,4 do
    local p=s[k]
    assert(math.abs(p[3]-(0.2*p[1]+0.1*p[2])-0.33)<0.0001,'height slider ignored area')
end end
assert(casts==queries,'height adjustment recast terrain')
''')

    def test_500kg_fills_disc_instead_of_bounding_square(self):
        replay(GUI+TYPES+FLAT+MENU+AREA+'''
type_rows[1].type=3
saved['eagle_direction_probe.show_ground_area']=true
frames(60)
local batch=area_faces()
assert(#batch>0 and #batch<=144,'circle is missing or too dense')
local total=projected_area(batch)
assert(total>1900 and total<1964,'circle has a hole, overlap, or square corners')
for _,s in ipairs(batch) do for k=2,4 do
    local p=s[k]
    assert(p[1]^2+p[2]^2<=625.001,'red fill escaped 25m reference circle')
end end
assert(max_frame<=2 and casts<=85,'circle fill added collision work')
''')

    def test_area_only_restores_saved_option_retains_faces_and_cleans_up_on_retirement(self):
        replay(GUI+TYPES+FLAT+MENU+AREA+'''
saved['eagle_direction_probe.show_ground_area']=true
for _,key in ipairs({'show_air','show_sky','show_ground_border','show_ground_triangles'}) do
    saved['eagle_direction_probe.'..key]=false
end
frames(60)
assert(#area_faces()>0 and max_frame<=2,'independent area-only mode did not sample terrain')
local queries,native_updates,native_creates=casts,updates,creates
local first=area_faces()[1]
frames(20)
assert(area_faces()[1]==first and updates==native_updates and creates==native_creates,
    'static red area rebuilt native geometry at animation frequency')
assert(casts==queries,'area-only mode resampled completed terrain')
apply('show_ground_area',false);frames(1)
assert(#area_faces()==0 and next(faces)==nil,'disabled area retained native faces')
values,rows,callbacks,writes={},{},{},{}
_G.ModOptionsMenu={api=1,register_option=host.register_option,get=host.get,
    set=host.set,on_change=host.on_change}
frames(25)
assert(not M.show_ground_area and not values['eagle_direction_probe.show_ground_area'],
    'saved false area option was replaced by default')
apply('show_ground_area',true);frames(1)
assert(#area_faces()>0)
M.tracks={};M.track_order={};M.impacts={};frames(1)
assert(next(faces)==nil and #area_faces()==0,'red area survived guide retirement')
''')

    def test_missing_collision_cells_remain_holes_without_flat_bridges(self):
        replay(GUI+TYPES+FLAT.replace("return 0, 'HIT'",
            "if x>=20 then return nil, 'MISS' end; return 0, 'HIT'")+MENU+AREA+'''
saved['eagle_direction_probe.show_ground_area']=true
frames(60)
local batch=area_faces()
assert(#batch>0,'valid half of terrain was hidden')
for _,s in ipairs(batch) do for k=2,4 do
    assert(s[k][1]<20,'area bridged an unknown terrain cell')
end end
''')

    def test_area_has_no_line_or_through_world_fallback(self):
        for renderer in ('', GUI):
            with self.subTest(solid=bool(renderer)):
                replay(renderer+TYPES+FLAT+MENU+AREA+'''
saved['eagle_direction_probe.show_ground_area']=true
frames(60)
if M.solid_active then assert(#area_faces()>0) else assert(#area_faces()==0) end
apply('through_world',true);frames(1)
assert(#area_faces()==0,'translucent area covered the screen through walls')
apply('through_world',false);apply('solid_fill',false);frames(1)
assert(#area_faces()==0,'area used scan-line fallback')
''')

    def test_rotated_teammate_areas_all_progress_with_one_global_query_budget(self):
        replay(GUI+TYPES+FLAT+MENU+AREA+'''
saved['eagle_direction_probe.show_ground_area']=true
M.tracks={};M.track_order={};M.impacts={};type_rows={}
for i=1,8 do
    type_rows[i]={type=18,p={i*300,0,0}}
    M.tracks[i]={trail={{i*300,0,80}},heading={0.6,0.8,0},seen=FAKE_TIME+1000}
    M.track_order[i]=i
    M.impacts[i]={p={i*300,0,0},heading={0.6,0.8,0},beacon=BEACON,
        last_seen=FAKE_TIME+1000,t=FAKE_TIME}
end
frames(300)
local batch=area_faces()
assert(math.abs(projected_area(batch)-19200)<0.01,
    'one or more teammate fills are missing: area='..projected_area(batch)..' casts='..casts..' faces='..#batch)
local owners={}
for _,s in ipairs(batch) do for k=2,4 do
    local p=s[k]
    local id=math.floor(p[1]/300+0.5)
    owners[id]=true
    local dx,dy=p[1]-id*300,p[2]
    assert(math.abs(dx*0.6+dy*0.8)<=60.001,'area ignored heading or beacon origin')
    assert(math.abs(-dx*0.8+dy*0.6)<=10.001,'area widened under rotation')
end end
for i=1,8 do assert(owners[i],'guide count was capped') end
assert(max_frame<=2 and casts<=8*85,'multiplayer area bypassed global terrain budget')
''')

    def test_unavailable_native_terrain_omits_area_instead_of_floating_at_beacon_height(self):
        replay(GUI+TYPES+FLAT.replace("return 0, 'HIT'", "return nil, 'UNAVAILABLE: fixture'")+MENU+AREA+'''
saved['eagle_direction_probe.show_ground_area']=true
frames(60)
assert(#area_faces()==0,'broad red surface used beacon-height fallback')
assert(not M.terrain_active and #M.seg>0,'existing guide fallback was removed')
''')

    def test_unknown_110mm_and_disabled_range_adaptation_do_not_claim_an_attack_area(self):
        for setting in ('type_rows[1].type=140', 'type_rows=nil',
                        "saved['eagle_direction_probe.adapt_range']=false"):
            with self.subTest(setting=setting):
                replay(GUI+TYPES+FLAT+MENU+AREA+setting+'''
saved['eagle_direction_probe.show_ground_area']=true
frames(60)
assert(#area_faces()==0,'direction-only guide was presented as an attack footprint')
assert(#M.seg>0,'unknown attack lost its original direction guide')
''')


if __name__ == '__main__': unittest.main()
