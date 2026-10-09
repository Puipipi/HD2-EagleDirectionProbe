"""Check the visible shapes produced by the real geometry/draw path."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lupa.luajit21 import LuaRuntime

REPO = Path(__file__).resolve().parents[1]
SCENE = """
M.tracks = { design = { trail = {{-20, 0, 80}, {0, 0, 80}},
    heading = {1, 0, 0}, seen = FAKE_TIME+1000 } }
M.track_order = {'design'}
M.impacts = { [1] = {p = {0, 0, 0}, heading = {1, 0, 0}, t = FAKE_TIME} }
package.preload['mods/codex/eagle_stratagem_profiles']=function()
    local p=os.getenv('DSH_PROBE_PATH'):gsub('eagle_direction_probe.lua$','stratagem_profiles.lua')
    return assert(loadfile(p))()
end
M.type_profiles=require('mods/codex/eagle_stratagem_profiles')
M.type_world=WORLD;M.type_epoch=tostring(WORLD)..':mission-one'
M.impacts[1].stratagem_type=18;M.impacts[1].type_epoch=M.type_epoch
M.impacts[1].type_heading_confirmed=true
M.adapt_range=false;M.show_type=false -- retain the generic silhouette fixture; typed extents are covered separately
M.impact_order = {1}
M.ground = {}
M.geom_key = nil
FAKE_TIME=FAKE_TIME+(DESIGN_PHASE or 0)
tick(1)
DESIGN_SEGMENTS = {}
for _,batch in ipairs({M.seg,M.flow_seg or {}}) do
    for _,segment in ipairs(batch) do DESIGN_SEGMENTS[#DESIGN_SEGMENTS+1]=segment end
end
"""


def design_geometry(phase=0):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / 'CowboyBingus/Helldivers2/Logs').mkdir(parents=True)
        with patch.dict(os.environ, {
                'DSH_HARNESS_TMP': tmp,
                'DSH_PROBE_PATH': str(REPO / 'src/eagle_direction_probe.lua'),
                'DSH_HARNESS_MODE': 'normal', 'DSH_FRAME_DT': '0.05'}):
            lua = LuaRuntime()
            lua.globals().DESIGN_PHASE=phase
            lua.execute('print = function() end')
            lua.execute((REPO / 'tests/offline/harness_draw.lua').read_text(encoding='utf-8')
                        + SCENE)
            segments = [[s[1], [s[2][i] for i in range(1, 4)],
                         [s[3][i] for i in range(1, 4)]]
                        for s in lua.globals().DESIGN_SEGMENTS.values()]
            state = lua.globals().HD2EagleDirectionProbe
            assert state.errors == 0 and (state.skipped or 0) == 0
            lua.globals().shutdown()
            return segments


class VisualGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.segments = design_geometry()

    def test_ground_has_sparse_forward_chevrons_and_a_center_diamond(self):
        ground = [s for s in self.segments if s[0] in ('ground', 'holo','flow') and s[1][2] < 1]
        self.assertLessEqual(len(ground), 450, 'bound the enlarged filled glyphs and thicker edges per pass')
        diagonal = [s for s in ground if abs(s[1][0] - s[2][0]) > 1
                    and abs(s[1][1] - s[2][1]) > 1]
        self.assertGreaterEqual(len(diagonal), 10, 'direction arrow silhouettes must be visible')
        marker = [s for s in self.segments if s[0] == 'marker']
        self.assertGreaterEqual(len(marker), 20, 'landing marker needs a bold, separate outline')
        self.assertAlmostEqual(max(s[k][2] for s in marker for k in (1, 2)), 3.6,
                               msg='compact upright diamond must stay at the actual beacon')
        self.assertLessEqual(max(abs(s[k][i]) for s in marker for k in (1, 2) for i in (0, 1)), 1.4)

    def test_ground_thick_solid_edges_and_lift(self):
        ground = [s for s in self.segments if s[0] in ('ground', 'holo') and s[1][2] < 1]
        edges = [s for s in ground if abs(s[1][1] - s[2][1]) < 0.001
                 and abs(s[1][0] - s[2][0]) >= 8]
        offsets = sorted(set(round(s[1][1], 3) for s in edges))
        self.assertGreaterEqual(len(offsets), 6)
        for side in ([o for o in offsets if o < 0], [o for o in offsets if o > 0]):
            self.assertGreaterEqual(len(side), 3)
            self.assertAlmostEqual(max(side) - min(side), 0.5, msg='fixed-width white band changed')
        self.assertLessEqual(max(abs(s[1][0] - s[2][0]) for s in edges), 15,
                             'long chords miss known changes in terrain height')
        self.assertTrue(all(0.03 <= s[k][2] <= 0.1 for s in ground for k in (1, 2)),
                        'keep the strip close to the sampled terrain without coplanar flicker')

    def test_air_arrow_stays_near_aircraft_and_trail_is_separate(self):
        air = [s for s in self.segments if s[0] == 'air']
        self.assertLessEqual(max(s[k][0] for s in air for k in (1, 2)), 200)
        self.assertTrue(any(s[0] == 'trail' for s in self.segments),
                        'the flown path needs its own dim colour')
        self.assertLessEqual(len(self.segments), 1250, 'cordon/text plus enlarged silhouettes have a bounded per-pass cost')


if __name__ == '__main__':
    unittest.main()
