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


def replay(scene):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / 'CowboyBingus/Helldivers2/Logs').mkdir(parents=True)
        with patch.dict(os.environ, {'DSH_HARNESS_TMP': tmp,
                        'DSH_PROBE_PATH': str(REPO / 'src/eagle_direction_probe.lua'),
                        'DSH_HARNESS_MODE': 'normal', 'DSH_FRAME_DT': '0.05'}):
            lua = LuaRuntime()
            lua.execute('print = function() end')
            try:
                lua.execute(SETUP + DEFAULT_EAGLE_TYPES + scene)
            except LuaError as error:
                raise AssertionError(str(error)) from error
            finally:
                if lua.globals().shutdown:
                    lua.globals().shutdown()
            state = lua.globals().HD2EagleDirectionProbe
            assert state.errors == 0, state.draw_error or state.trail_error


class MissionFeedbackTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
