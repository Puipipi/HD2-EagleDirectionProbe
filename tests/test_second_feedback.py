"""Second mission: shorten guides, retire on departure, preserve sampled slopes."""
import unittest

from test_mission_feedback import replay

FLIGHT = '''
local p, f = {-600, 0, 400}, {0.8, 0, -0.6}
local old_pos = sr.Unit.world_position
sr.Unit.world_position = function(unit)
    if unit == AIRCRAFT then return p end
    return old_pos(unit)
end
sr.Matrix4x4.forward = function() return f end
tick(30)
ST.beacon_arc, ST.aircraft_up = 1, true
tick(4)
ST.beacon_arc = 5
p = {-100, 0, 100}
tick(20)
assert(next(M.impacts) ~= nil, 'fixture must reach a bound strike')
'''


class SecondMissionFeedbackTest(unittest.TestCase):
    def test_departure_hides_both_guides_while_aircraft_still_exists(self):
        replay(FLIGHT + '''
p, f = {200, 0, 150}, {0.8, 0, 0.6}
tick(20)
assert(#sr.World.units_by_resource(WORLD,
    'content/fac_helldivers/vehicles/eagle/eagle') == 1, 'fixture aircraft must remain')
assert(next(M.impacts) == nil, 'ground remains after confirmed departure')
assert(not FRAME_HAS_LINES and M.seg_count == 0, 'air arrow remains after departure')
tick(80)
assert(not FRAME_HAS_LINES, 'departing aircraft was rediscovered and redrawn')
''')

    def test_a_momentary_upward_tilt_does_not_end_the_strike(self):
        replay(FLIGHT + '''
p, f = {-80, 0, 105}, {0.8, 0, 0.6}
tick(2)
p, f = {-40, 0, 100}, {1, 0, 0}
tick(20)
assert(next(M.impacts) ~= nil and FRAME_HAS_LINES, 'a transient tilt hid the live strike')
''')

    def test_arrow_and_ground_are_shorter_but_keep_a_readable_head(self):
        replay('''
M.tracks = { design = {trail = {{0, 0, 80}}, heading = {1, 0, 0}, seen = FAKE_TIME} }
M.impacts = {[1] = {p = {0, 0, 0}, heading = {1, 0, 0}, t = FAKE_TIME}}
M.geom_key = nil
tick(1)
local alo, ahi, glo, ghi = math.huge, -math.huge, math.huge, -math.huge
for _, s in ipairs(M.seg or {}) do
    for k = 2, 3 do
        if s[1] == 'air' then
            alo, ahi = math.min(alo, s[k][1]), math.max(ahi, s[k][1])
        elseif s[1] == 'ground' or s[1] == 'holo' and s[k][3] < 2 then
            glo, ghi = math.min(glo, s[k][1]), math.max(ghi, s[k][1])
        end
    end
end
assert(ahi - alo <= 360 and ahi >= 100, 'air guide still dominates the scene')
assert(ghi - glo <= 205 and ghi - glo >= 150, 'ground warning is still too long')
''')

    def test_known_planar_slope_is_not_flattened_by_distance_averaging(self):
        replay('''
M.tracks = {design = {trail = {{30, 30, 80}}, heading = {1, 0, 0}, seen = FAKE_TIME}}
M.impacts = {[1] = {p = {30, 30, 9}, heading = {1, 0, 0}, t = FAKE_TIME}}
-- Hand-defined terrain plane z = 0.2*x + 0.1*y, sampled at three non-collinear points.
M.ground = {{0, 0, 0, FAKE_TIME}, {100, 0, 20, FAKE_TIME}, {0, 100, 10, FAKE_TIME}}
M.geom_key = nil
tick(1)
local n = 0
for _, s in ipairs(M.seg or {}) do
    if s[1] == 'ground' then
        for k = 2, 3 do
            local x, y, z = s[k][1], s[k][2], s[k][3]
            if x >= 0 and y >= 0 and x + y <= 100 and z < 40 then
                n = n + 1
                assert(math.abs(z - (0.2*x + 0.1*y + 0.08)) < 0.15,
                    'known slope was flattened instead of followed')
            end
        end
    end
end
assert(n >= 10, 'fixture must inspect terrain edges inside the sampled triangle')
''')


if __name__ == '__main__':
    unittest.main()
