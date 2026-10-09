"""Regressions for the four observations from the first 1.9.0 mission."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lupa.luajit21 import LuaError, LuaRuntime

REPO = Path(__file__).resolve().parents[1]
HARNESS = (REPO / 'tests/offline/harness_draw.lua').read_text(encoding='utf-8')
SETUP = HARNESS.split("tick(30)\nreport('on the ship')", 1)[0]
THROW = '''
tick(30)
ST.beacon_arc = 1
ST.aircraft_up = true
tick(4)
ST.beacon_arc = 5
tick(60)
assert(next(M.impacts) ~= nil, 'fixture must reach a landed strike')
'''

# Ordinary replay scenes represent an identified Eagle. Classification-specific
# tests replace these lazy modules with their own snapshots (including unknowns).
DEFAULT_EAGLE_TYPES = '''
package.preload['mods/codex/eagle_stratagem_profiles']=function()
    local p=os.getenv('DSH_PROBE_PATH'):gsub('eagle_direction_probe.lua$','stratagem_profiles.lua')
    return assert(loadfile(p))()
end
package.preload['mods/codex/eagle_stratagem_query']=function()
    return {new=function() return {snapshot=function()
        local p=sr.Unit.world_position(BEACON)
        if ST.beacon_arc>0 then
            return p and {{type=18,p=p,anchor={p[1],p[2]+100,p[3]}}} or {},'READY','mission-one'
        end
        -- Pure renderer fixtures may seed explicit impacts without simulating a throw.
        -- The ordinary replay represents those fixtures as confirmed Eagle calls; tests
        -- about unknown/unsupported types install their own reader before polling.
        local probe=rawget(_G,'HD2EagleDirectionProbe')
        local rows={}
        for _,imp in pairs(probe and probe.impacts or {}) do
            local q=imp.p
            if q then rows[#rows+1]={type=18,p=q,anchor={q[1],q[2]+100,q[3]}} end
        end
        return rows,'READY','mission-one'
    end} end}
end
'''


def replay(scene, prelude=''):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / 'CowboyBingus/Helldivers2/Logs').mkdir(parents=True)
        with patch.dict(os.environ, {'DSH_HARNESS_TMP': tmp,
                        'DSH_PROBE_PATH': str(REPO / 'src/eagle_direction_probe.lua'),
                        'DSH_HARNESS_MODE': 'normal', 'DSH_FRAME_DT': '0.05'}):
            lua = LuaRuntime()
            lua.execute('print = function() end')
            try:
                lua.execute(prelude + SETUP + DEFAULT_EAGLE_TYPES + scene)
            except LuaError as error:
                raise AssertionError(str(error)) from error
            finally:
                if lua.globals().shutdown:
                    lua.globals().shutdown()
            state = lua.globals().HD2EagleDirectionProbe
            assert state.errors == 0, state.draw_error or state.trail_error


class MissionFeedbackTest(unittest.TestCase):
    def test_precision_clock_status_separates_cpu_cost_from_frame_gap(self):
        replay('''
FAKE_TIME=200;update()
assert(M.clock_source=='fixture' and M.clock_precise==true,
    'offline timing fixture did not explicitly identify its source')
assert(M.tick_timed_samples>0 and M.draw_timed_samples>0,
    'guarded hotpath and draw timing were not accumulated')
local f=assert(io.open(os.getenv('LOCALAPPDATA')..'/CowboyBingus/Helldivers2/Logs/EagleDirectionProbe.log','r'))
local text=f:read('*a');f:close()
assert(text:find('clock=fixture/true',1,true) and text:find('tick_avg=',1,true)
    and text:find('draw_active=',1,true) and text:find('frame_gap_peak=',1,true),
    'status must identify clock source and report CPU work separately from frame gaps')
''')

    def test_finished_strike_clears_without_waiting_for_another_throw(self):
        replay(THROW + '''
ST.aircraft_up = false
ST.beacon_arc = 0
tick(70)  -- 3.5 seconds, with no subsequent calls to evict the strip
assert(next(M.impacts) == nil, 'finished strike still has a ground strip')
assert(not FRAME_HAS_LINES, 'expired geometry must actually be hidden')
assert(M.seg_count == 0, 'status must report cleared geometry')
''')

    def test_brief_beacon_query_gap_does_not_clear_the_warning(self):
        replay(THROW + '''
ST.beacon_arc = 0
tick(10)  -- half a second, longer than the measured occasional missed query
assert(next(M.impacts) ~= nil, 'a short query gap must not hide a live strike')
ST.beacon_arc = 5
tick(5)
assert(next(M.impacts) ~= nil, 'same beacon must recover after a short gap')
''')

    def test_other_beacon_cannot_keep_a_finished_strike_alive(self):
        replay(THROW + '''
ST.aircraft_up = false
local query = sr.World.units_by_resource
local other = {}
local position = sr.Unit.world_position
sr.Unit.world_position = function(unit)
    if unit == other then return {500, 500, 32} end
    return position(unit)
end
sr.World.units_by_resource = function(world, key)
    if key == '16f397ca5f51f271' then return {other} end
    return query(world, key)
end
tick(70)
assert(next(M.impacts) == nil, 'an unrelated beacon kept an old strip alive')
''')

    def test_ground_waits_for_its_aircraft_even_after_beacon_disappears(self):
        replay(THROW + '''
ST.beacon_arc = 0
tick(70)
assert(next(M.tracks) ~= nil, 'fixture aircraft must still be flying')
assert(next(M.impacts) ~= nil, 'ground guide ended before the aircraft guide')
ST.aircraft_up = false
tick(35)
assert(next(M.impacts) == nil, 'ground guide must end with its aircraft guide')
''')

    def test_lingering_beacon_does_not_outlive_its_aircraft_guide(self):
        replay(THROW + '''
ST.aircraft_up = false
tick(35)
assert(next(M.impacts) == nil, 'lingering beacon kept a finished aircraft strip')
tick(20)
assert(next(M.impacts) == nil, 'same settled beacon recreated its retired strip')
''')

    def test_removing_one_cached_guide_rebuilds_ground_membership(self):
        replay(THROW + '''
local epoch=tostring(WORLD)..':mission-one'
M.type_profiles=require('mods/codex/eagle_stratagem_profiles')
M.type_world,M.type_epoch=WORLD,epoch
M.type_next=FAKE_TIME+100
M.stopped=true
M.impacts,M.impact_order={},{}
M.tracks,M.track_order={},{}
M.terrain_active=true;M.terrain_world=WORLD;M.terrain_provider={height=function()
    error('completed offline terrain cache must not query') end}
M.terrain_queries=0;M.ground_revision=68;M.ground_geom_key=nil;M.ground_seg=nil
local function grid(x)
    local g={x=x,y=0,z=0,hx=1,hy=0,lo=-100.25,hi=100.25,half=12,
        n=24,rows=3,row_offsets={-12,0,12},
        h={},order={},cursor=76,born=FAKE_TIME}
    for k=0,24 do for row=1,3 do
        g.h[k*3+row]=0;g.order[#g.order+1]={k,row}
    end end
    return g
end
local departed,alive={},{}
M.tracks[alive]={trail={{300,0,80}},heading=nil,seen=FAKE_TIME+100,finished=false}
for id,x in pairs({
    [901]={100,departed},[902]={300,alive},
}) do
    M.impacts[id]={p={x[1],0,0},heading={1,0,0},aircraft=x[2],
        stratagem_type=18,type_heading_confirmed=true,type_epoch=epoch,
        born=FAKE_TIME+100,last_seen=FAKE_TIME+100,t=FAKE_TIME,terrain=grid(x[1]),
        type_display_started=FAKE_TIME,type_display_wait=false}
    M.impact_order[#M.impact_order+1]=id
end
M.track_order={alive};M.geom_key,M.flow_key=nil,nil
M.corridor_next=FAKE_TIME*1000+5000
local function upvalue(fn,wanted)
    for i=1,debug.getinfo(fn,'u').nups do
        local name,value=debug.getupvalue(fn,i)
        if name==wanted then return value end
    end
end
local guarded=assert(upvalue(update,'guarded'))
local corridor=assert(upvalue(guarded,'corridor_tick'))
local draw=assert(upvalue(guarded,'draw_corridor'))
draw()
assert(M.geometry_key_ground:find('901:',1,true)
    and M.geometry_key_ground:find('902:',1,true),'fixture must cache both guides')
assert(M.geom_key~=nil and M.draw_frames>0,'fixture did not build a retained render key')
local before_builds,before_revision=M.ground_builds,M.ground_revision
M.corridor_next=0
corridor()
assert(M.impacts[901]==nil and M.impacts[902]~=nil,
    'finished aircraft should retire only its own guide')
assert(M.geom_key==nil and M.ground_geom_key==nil,
    'removing one strike must dirty both cached geometry keys')
draw()
assert(not M.geometry_key_ground:find('901:',1,true)
    and M.geometry_key_ground:find('902:',1,true),
    'cached ground membership retained a removed guide')
assert(M.ground_builds>before_builds and M.ground_revision==before_revision
    and M.terrain_queries==0,'membership rebuild must reuse the completed terrain grid')
''')

    def test_an_unrelated_aircraft_does_not_keep_the_old_ground_guide(self):
        replay(THROW + '''
local query = sr.World.units_by_resource
sr.World.units_by_resource = function(world, key)
    if key == 'content/fac_helldivers/vehicles/eagle/eagle' then return {AIRCRAFT2} end
    return query(world, key)
end
tick(35)
assert(M.tracks[AIRCRAFT2] ~= nil, 'other aircraft guide should remain')
assert(next(M.impacts) == nil, 'unrelated aircraft kept the old ground guide')
''')

    def test_live_guides_are_not_evicted_by_number(self):
        replay('''
M.tracks, M.impacts = {}, {}
for i = 1, 7 do
    M.tracks[i] = {trail = {{i * 50, 0, 80}}, heading = {1, 0, 0}, seen = FAKE_TIME}
    M.impacts[i] = {p = {i * 50, 0, 0}, heading = {1, 0, 0}, t = FAKE_TIME,
        born = FAKE_TIME, aircraft = i}
end
M.geom_key = nil
tick(1)
assert(#M.track_order == 7, 'live aircraft were evicted by a numerical cap')
assert(#M.impact_order == 7, 'live strips were evicted by a numerical cap')
''')

    def test_ground_strip_has_compact_closed_travelling_heads(self):
        replay('''
M.tracks = { design = {trail = {{0, 0, 80}}, heading = {1, 0, 0}, seen = FAKE_TIME} }
M.impacts = { [1] = {p = {0, 0, 0}, heading = {1, 0, 0}, stratagem_type=18, t = FAKE_TIME} }
M.type_profiles=require('mods/codex/eagle_stratagem_profiles')
M.type_world=WORLD;M.type_epoch='world:mission-one';M.impacts[1].type_epoch=M.type_epoch
M.type_next=FAKE_TIME+100
M.geom_key = nil
tick(1)
local function key(v) return string.format('%.4f,%.4f',v[1],v[2]) end
local function joined(a,b,on_side)
    local graph={}
    for _,s in ipairs(M.flow_seg or {}) do
        if s[1]=='flow' and on_side(s[2]) and on_side(s[3]) then
            local x,y=key(s[2]),key(s[3])
            graph[x]=graph[x] or {}; graph[y]=graph[y] or {}
            graph[x][y]=true; graph[y][x]=true
        end
    end
    local seen,queue={}, {key(a)}
    for _,v in ipairs(queue) do
        if v==key(b) then return true end
        for w in pairs(graph[v] or {}) do
            if not seen[w] then seen[w]=true; queue[#queue+1]=w end
        end
    end
    return false
end
local tip
for _,s in ipairs(M.flow_seg) do
    if s[1]=='flow' and math.abs(s[3][2])<0.001 and s[2][2]<-2 then tip=s[3]; break end
end
assert(tip,'travelling head outline is missing')
local t=tip[1]
assert(joined({t-5.2,-2.9},{t,0},function(v)
    return math.abs(v[2]-(v[1]-t)*(2.9/5.2))<0.001 end), 'left head side is broken')
assert(joined({t,0},{t-5.2,2.9},function(v)
    return math.abs(v[2]+(v[1]-t)*(2.9/5.2))<0.001 end), 'right head side is broken')
assert(joined({t-5.2,2.9},{t-5.2,-2.9},function(v)
    return math.abs(v[1]-(t-5.2))<0.001 end), 'ground head has no closed base')
''')

    def test_ground_direction_follows_approach_but_not_departure_turn(self):
        replay(THROW + '''
sr.Matrix4x4.forward = function() return {0, 1, 0} end
tick(5)
local imp = M.impacts[next(M.impacts)]
assert(imp.heading[2] > 0.9, 'ground direction ignored the live approach turn')
sr.Matrix4x4.forward = function() return {0, -1, 0.9} end
tick(5)
assert(M.tracks[imp.aircraft].heading[2] < 0, 'fixture aircraft must turn away')
assert(imp.heading[2] > 0.9, 'departure turn reversed the ground incoming direction')
''')

    def test_landing_marker_is_compact_and_visible_from_ground_level(self):
        replay(THROW + '''
local imp = next(M.impacts) and M.impacts[next(M.impacts)]
local lo, hi, top = math.huge, -math.huge, imp.p[3]
local n = 0
for _, s in ipairs(M.seg or {}) do
    if s[1] == 'marker' then
        n = n + 1
        for k = 2, 3 do
            local dx, dy = s[k][1] - imp.p[1], s[k][2] - imp.p[2]
            lo = math.min(lo, dx, dy)
            hi = math.max(hi, dx, dy)
            top = math.max(top, s[k][3])
        end
    end
end
assert(n >= 35 and hi - lo >= 1.5 and hi-lo<=3, 'landing marker must be filled and compact')
assert(top >= imp.p[3] + 3.5 and top<=imp.p[3]+3.7, 'small upright diamond has incorrect height')
''')

    def test_air_guidance_retains_close_head_but_has_a_long_stem(self):
        replay('''
M.tracks = { design = {trail = {{0, 0, 80}}, heading = {1, 0, 0}, seen = FAKE_TIME} }
M.track_order = {'design'}
M.impacts = {}
M.geom_key = nil
tick(1)
local lo, hi = math.huge, -math.huge
for _, s in ipairs(M.seg or {}) do
    if s[1] == 'air' then
        lo = math.min(lo, s[2][1], s[3][1])
        hi = math.max(hi, s[2][1], s[3][1])
    end
end
assert(lo <= -180, 'air guidance has no incoming stem')
assert(hi >= 100 and hi <= 150, 'keep the shortened near-aircraft arrowhead')
''')

    def test_active_timing_bucket_persists_between_samples_and_clears_on_session_end(self):
        replay(THROW + '''
assert(M.last_tick_active==true,'fixture must be inside a live mission')
local active_samples=M.active_tick_samples or 0
local calls=M.samples
FAKE_TIME=FAKE_TIME+0.05
update()
assert(M.samples==calls,'test frame must occur between the 5 Hz source samples')
assert(M.last_tick_active==true and M.active_tick_samples>active_samples,
    'unsampled mission frames were classified as idle')
sr.GameSession.in_session=function() return false end
FAKE_TIME=FAKE_TIME+1
update()
assert(M.last_tick_active==false,'session end did not clear the active timing state')
''')


if __name__ == '__main__':
    unittest.main()
