"""Integration checks for display-bounds-driven terrain sampling."""
import unittest

from test_mission_feedback import replay

class TerrainPrecisionTest(unittest.TestCase):
    def test_each_confirmed_shape_uses_a_finer_bounded_cached_grid(self):
        replay('''
local samples, per_tick = {}, 0
package.preload['mods/codex/eagle_terrain_query']=function()
    return {new=function() return {height=function(self,sr,world,unit,x,y,z)
        samples[#samples+1]={x=x,y=y};per_tick=per_tick+1
        return x*0.1+y*0.2,'HIT'
    end} end}
end
M.type_profiles=require('mods/codex/eagle_stratagem_profiles')
M.type_world,M.type_epoch=WORLD,tostring(WORLD)..':mission-one'
M.type_provider={};M.type_next=FAKE_TIME*1000+100000
M.terrain_world=WORLD;M.terrain_provider=nil;M.terrain_active=true
M.impacts={[1]={p={0,0,0},heading={1,0,0},beacon=BEACON,
    stratagem_type=18,type_heading_confirmed=true,type_epoch=M.type_epoch,
    born=FAKE_TIME,last_seen=FAKE_TIME,t=FAKE_TIME}}
M.impact_order={1};M.ground_revision=0
local function upvalue(fn,wanted)
    for i=1,debug.getinfo(fn,'u').nups do
        local name,value=debug.getupvalue(fn,i)
        if name==wanted then return value end
    end
end
local guarded=assert(upvalue(update,'guarded'))
local terrain_tick=assert(upvalue(guarded,'terrain_tick'))
local function sample_shape(id,n,rows,total,lo,hi,width)
    local imp=M.impacts[1]
    imp.stratagem_type=id;imp.terrain=nil
    M.terrain_provider=nil;M.terrain_world=WORLD
    samples={};M.terrain_queries=0;M.terrain_round=0
    terrain_tick()
    local g=assert(imp.terrain,'terrain grid was not created')
    assert(g.n==n and g.rows==rows and #g.order==total,
        'wrong sample-grid plan for type '..id..': '..tostring(g.n)..'x'
            ..tostring(g.rows)..'/'..tostring(#g.order))
    assert(math.abs(g.lo-lo)<0.001 and math.abs(g.hi-hi)<0.001
        and math.abs(g.half-width)<0.001,'grid does not follow display bounds')
    local plan_ref=imp.terrain_plan.plan
    assert(#samples<=2,'terrain planning exceeded the two-query frame budget')
    for _=1,50 do
        per_tick=0;terrain_tick()
        assert(per_tick<=2,'terrain query budget exceeded on a later frame')
        assert(imp.terrain_plan.plan==plan_ref,'stationary ticks reallocated the sample plan')
        if g.cursor>#g.order then break end
    end
    assert(g.cursor>#g.order,'planned grid did not complete')
    assert(M.terrain_queries==total,'terrain sample count differs from plan')
    local step=(hi-lo)/n
    assert(samples[1] and math.abs(samples[1].x)<=step/2+0.001
        and math.abs(samples[1].y)<=0.001,
        'sample order must begin at the axial station nearest the impact')
end
sample_shape(18,10,5,55,-100/3-0.25,100/3+0.25,10.5)
sample_shape(3,8,7,63,-25.5,25.5,25.5)
sample_shape(140,24,3,75,-100.25,100.25,6.5)
sample_shape(30,10,5,55,-5.25,55.25,5.5)
local strike_grid=M.impacts[1].terrain
local origin_k=strike_grid.origin_k
local origin_t=strike_grid.lo+(strike_grid.hi-strike_grid.lo)*origin_k/strike_grid.n
local strike_height=strike_grid.h[origin_k*strike_grid.rows+(strike_grid.rows+1)/2]
assert(math.abs(origin_t)>0.1 and math.abs(strike_height-origin_t*0.1)<0.001,
    'nearest strafe station must retain its measured terrain height, not beacon height')
local imp=M.impacts[1]
local previous=imp.terrain_plan.plan
M.adapt_range=false;imp.terrain=nil
terrain_tick()
assert(imp.terrain_plan.plan~=previous and imp.terrain_plan.adaptive==false,
    'switching to generic display bounds must replace the cached plan')
assert(imp.terrain_plan.plan.lo==-100.25 and imp.terrain_plan.plan.hi==100.25,
    'generic bounds did not invalidate the type-specific plan')
''')

    def test_ground_border_mesh_uses_cached_axial_stations_and_keeps_ridge_peak(self):
        replay('''
local function upvalue(fn,wanted)
    for i=1,debug.getinfo(fn,'u').nups do
        local name,value=debug.getupvalue(fn,i)
        if name==wanted then return value end
    end
end
local guarded=assert(upvalue(update,'guarded'))
local draw=assert(upvalue(guarded,'draw_corridor'))
local build=assert(upvalue(draw,'build_geometry'))
local gridmod=require('mods/codex/eagle_terrain_grid')
local profiles=require('mods/codex/eagle_stratagem_profiles')
local bounds=profiles.bounds(18)
local plan=assert(gridmod.plan(bounds,0.25))
local peak_k=math.floor(plan.n/2)
local peak_t=plan.lo+(plan.hi-plan.lo)*peak_k/plan.n
local grid={x=0,y=0,z=0,hx=1,hy=0,lo=plan.lo,hi=plan.hi,width=plan.width,
    n=plan.n,rows=plan.rows,row_offsets=plan.row_offsets,h={},origin_k=peak_k}
for k=0,grid.n do
    for row=1,grid.rows do
        grid.h[k*grid.rows+row]=k==peak_k and 12 or 0
    end
end
local epoch=tostring(WORLD)..':mesh-station-test'
local impact={p={0,0,0},heading={1,0,0},beacon=BEACON,
    stratagem_type=18,type_heading_confirmed=true,type_epoch=epoch,terrain=grid,
    born=FAKE_TIME,last_seen=FAKE_TIME,t=FAKE_TIME}
M.type_profiles=profiles;M.type_epoch=epoch;M.adapt_range=true
M.impacts={[1]=impact};M.tracks={};M.track_order={};M.ground_seg=nil
M.ground_revision=1;M.ground_geom_key=nil;M.terrain_active=true
M.show_ground_border=true;M.show_ground_triangles=false;M.show_sky=false
M.show_air=false;M.show_cordon=false;M.solid_active=false
build('station-aligned-test')
local stations=assert(gridmod.stations(grid,bounds.lo,bounds.hi))
local observed={};local peak=false
for _,s in ipairs(M.ground_seg) do
    if s[1]=='ground' and not s[4] then
        for _,p in ipairs({s[2],s[3]}) do
            if math.abs(p[2]-10)<1e-7 then
                for _,t in ipairs(stations) do
                    if math.abs(p[1]-t)<1e-7 then
                        observed[t]=true
                        if math.abs(t-peak_t)<1e-7 and p[3]>12 then peak=true end
                    end
                end
            end
        end
    end
end
for _,t in ipairs(stations) do
    assert(observed[t], 'ground border skipped cached terrain station '..tostring(t))
end
assert(peak,'edge mesh skipped the sampled terrain peak instead of placing a vertex over it')
''')


if __name__ == '__main__':
    unittest.main()
