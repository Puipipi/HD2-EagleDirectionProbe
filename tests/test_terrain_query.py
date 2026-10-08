"""Actual probe geometry over distant terrain; native calls use an injectable boundary."""
import unittest

from test_mission_feedback import replay


SCENE = '''
local casts, max_frame = 0, 0
local in_frame = 0
package.loaded['mods/codex/eagle_terrain_query'] = nil
package.preload['mods/codex/eagle_terrain_query'] = function()
    return {new = function()
        return {height = function(self, sr, world, unit, x, y, z)
            casts, in_frame = casts + 1, in_frame + 1
            -- A ridge 60 m away. The only beacon is on the flat at x=0.
            return math.max(0, 30 - math.abs(x - 60)), 'HIT'
        end}
    end}
end
M.tracks = {design = {trail = {{0, 0, 80}}, heading = {1, 0, 0}, seen = FAKE_TIME + 1000}}
M.impacts = {[1] = {p = {0, 0, 0}, heading = {1, 0, 0}, beacon = BEACON, last_seen=FAKE_TIME+1000, t = FAKE_TIME}}
M.ground = {{0, 0, 0, FAKE_TIME}}
M.geom_key = nil
local function frames(n)
    for i=1,n do
        in_frame = 0
        tick(1)
        max_frame = math.max(max_frame, in_frame)
    end
end
'''


class TerrainQueryTest(unittest.TestCase):
    def test_distant_ridge_changes_actual_ground_vertices(self):
        replay(SCENE + '''
frames(45)
local high = 0
for _, s in ipairs(M.seg or {}) do
    if s[1] == 'holo' or s[1] == 'ground' then
        for i=2,3 do
            local p=s[i]
            if p[1] > 50 and p[1] < 70 and p[3] > 15 and p[3] < 40 then high=high+1 end
        end
    end
end
assert(high >= 8, 'distant ridge was flattened to the beacon height')
assert(casts > 0 and casts <= 70, 'grid must be queried once and cached')
assert(max_frame <= 2, 'terrain query budget exceeded')
local old=casts
frames(30)
assert(casts == old, 'stationary corridor was queried every frame')
''')

    def test_many_corridors_share_a_global_budget_and_all_progress(self):
        replay(SCENE + '''
for i=2,7 do
    M.impacts[i] = {p={i*300,0,0},heading={1,0,0},beacon=BEACON,last_seen=FAKE_TIME+1000,t=FAKE_TIME}
end
frames(240)
assert(max_frame <= 2, 'budget must cover all corridors together')
assert(casts >= 7*60, 'some corridors starved or were capped')
assert(casts <= 7*70, 'completed terrain grids should be cached')
''')

    def test_missing_hits_do_not_draw_a_flat_bridge_through_unknown_terrain(self):
        replay(SCENE + '''
package.preload['mods/codex/eagle_terrain_query'] = function()
    return {new=function() return {height=function(self,sr,world,unit,x,y,z)
        casts, in_frame=casts+1,in_frame+1
        if x>40 then return nil,'MISS' end
        return 0,'HIT'
    end} end}
end
frames(45)
for _,s in ipairs(M.seg or {}) do
    if s[1]=='ground' or s[1]=='holo' then
        for k=2,3 do
            assert(not (s[k][1]>45 and s[k][3]<2), 'a missed ray became fake flat ground')
        end
    end
end
assert(FRAME_HAS_LINES, 'air guide and sampled ground should remain visible')
''')

    def test_turn_refreshes_terrain_and_disappearing_calls_stop_queries(self):
        replay(SCENE + '''
frames(40)
local old=casts
M.impacts[1].heading={0,1,0}
M.tracks.design.heading={0,1,0}
M.geom_key=nil
frames(40)
assert(casts > old+50, 'a turned corridor reused the wrong terrain grid')
M.impacts={}
old=casts
frames(20)
assert(casts==old, 'retired corridors still query terrain')
''')

    def test_soft_time_budget_stops_before_a_second_slow_query(self):
        replay(SCENE + '''
local extra=0
sr.Application.time_since_launch=function() return FAKE_TIME+extra end
local old=package.preload['mods/codex/eagle_terrain_query']
package.preload['mods/codex/eagle_terrain_query']=function()
    local factory=old()
    return {new=function()
        local q=factory.new()
        local height=q.height
        q.height=function(...)
            extra=extra+0.001 -- deterministic 1 ms at the real boundary
            return height(...)
        end
        return q
    end}
end
frames(40)
assert(casts>0 and max_frame==1,'a slow query was followed by another in the same frame')
''')

    def test_small_steering_changes_do_not_restart_the_cached_grid(self):
        replay(SCENE + '''
frames(40)
local old=casts
M.tracks.design.heading={0.99995,0.01,0}
frames(30)
assert(casts==old,'minor steering restarted terrain sampling')
''')

    def test_140_fps_still_limits_actual_updates_to_two_queries(self):
        replay(SCENE + '''
for i=1,140 do
    in_frame=0
    FAKE_TIME=FAKE_TIME+1/140
    _G.update()
    assert(in_frame<=2,'high FPS multiplied the per-frame native workload')
end
assert(casts==63,'one second should complete and cache the stationary grid')
''')

    def test_ground_arrow_sides_also_follow_the_cached_surface(self):
        scene=SCENE.replace('30 - math.abs(x - 60)', '20 - 2*math.abs(x - 85)')
        replay(scene + '''
frames(45)
FAKE_TIME=200
frames(1)
local high=0
for _,s in ipairs(M.flow_seg or {}) do
    if s[1]=='flow' and math.abs(s[2][2]-s[3][2])>0.5 then
        for k=2,3 do
            if s[k][1]>77 and s[k][1]<96 and s[k][3]>8 then high=high+1 end
        end
    end
end
assert(high>=4,'filled arrow rows bridged the ridge instead of following sampled heights')
''')


if __name__ == '__main__':
    unittest.main()
