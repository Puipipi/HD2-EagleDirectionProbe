"""Pure grid planning and interpolation for cached Eagle terrain samples."""
import math
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / 'src/terrain_grid.lua'


class TerrainGridTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        load = self.lua.eval("function(path) return assert(loadfile(path))() end")
        self.grid = load(str(MODULE))

    def plan(self, shape, lo, hi, half, radius=None):
        bounds = self.lua.table_from({
            'shape': shape, 'lo': lo, 'hi': hi, 'half': half,
        })
        if radius is not None:
            bounds['radius'] = radius
        return self.grid.plan(bounds)

    def test_strips_use_five_evenly_spaced_rows_inside_the_required_margin(self):
        p = self.plan('strip', -100 / 3, 100 / 3, 10)
        self.assertAlmostEqual(p.lo, -100 / 3 - 0.25)
        self.assertAlmostEqual(p.hi, 100 / 3 + 0.25)
        self.assertAlmostEqual(p.width, 10.5)
        self.assertEqual((p.n, p.rows, p.total), (10, 5, 55))
        self.assertEqual([p.row_offsets[i] for i in range(1, 6)],
                         [-10.5, -5.25, 0, 5.25, 10.5])

    def test_circle_and_long_direction_plans_fit_their_consumers_and_budget(self):
        circle = self.plan('circle', -25, 25, 25, 25)
        self.assertEqual((circle.lo, circle.hi, circle.width), (-25.5, 25.5, 25.5))
        self.assertEqual((circle.n, circle.rows, circle.total), (8, 7, 63))

        direction = self.plan('direction', -100, 100, 6)
        self.assertEqual((direction.lo, direction.hi, direction.width),
                         (-100.25, 100.25, 6.5))
        self.assertEqual((direction.n, direction.rows, direction.total), (24, 3, 75))
        self.assertLessEqual(direction.total, 85)
        self.assertEqual(direction.n % 2, 0)

    def test_signature_tracks_geometry_without_mutating_the_profile(self):
        bounds = self.lua.table_from({
            'shape': 'strip', 'lo': -100 / 3, 'hi': 100 / 3, 'half': 10,
        })
        original = (bounds.lo, bounds.hi, bounds.half)
        a = self.grid.plan(bounds)
        b = self.grid.plan(bounds)
        other = self.plan('strip', -30, 30, 10)
        self.assertEqual(a.signature, b.signature)
        self.assertNotEqual(a.signature, other.signature)
        self.assertEqual((bounds.lo, bounds.hi, bounds.half), original)

    def test_invalid_bounds_fail_closed(self):
        cases = [
            self.lua.table_from({'shape': 'strip', 'lo': 1, 'hi': 1, 'half': 2}),
            self.lua.table_from({'shape': 'circle', 'lo': -1, 'hi': 1, 'half': 1}),
            self.lua.table_from({'shape': 'other', 'lo': -1, 'hi': 1, 'half': 1}),
            self.lua.table_from({'shape': 'strip', 'lo': -1, 'hi': 1, 'half': -1}),
            self.lua.table_from({'shape': 'strip', 'lo': float('nan'), 'hi': 1, 'half': 1}),
        ]
        for bounds in cases:
            with self.subTest(bounds=str(bounds)):
                self.assertIsNone(self.grid.plan(bounds))
        self.assertIsNone(self.grid.plan(self.lua.table_from({
            'shape': 'strip', 'lo': -1, 'hi': 1, 'half': 1,
        }), -1))

    def make_sampled_grid(self, plan, height):
        grid = self.lua.table()
        for key in ('lo', 'hi', 'width', 'n', 'rows', 'row_offsets', 'total', 'signature'):
            grid[key] = plan[key]
        grid.h = self.lua.table()
        for k in range(plan.n + 1):
            along = plan.lo + (plan.hi - plan.lo) * k / plan.n
            for row in range(1, plan.rows + 1):
                lateral = plan.row_offsets[row]
                grid.h[k * plan.rows + row] = height(along, lateral)
        return grid

    def test_bilinear_interpolation_is_exact_for_a_plane_and_does_not_bridge_misses(self):
        p = self.plan('strip', -100 / 3, 100 / 3, 10)
        expected = lambda x, y: 2 * x - 3 * y + 7
        grid = self.make_sampled_grid(p, expected)
        sample = (p.lo + p.hi) / 2 + 1.25
        lateral = 2.1
        self.assertAlmostEqual(self.grid.height(grid, sample, lateral),
                               expected(sample, lateral), places=10)

        cell_x = p.lo + (p.hi - p.lo) * 4.25 / p.n
        cell_y = -p.width + 0.4 * (2 * p.width / (p.rows - 1))
        k = math.floor((cell_x - p.lo) * p.n / (p.hi - p.lo))
        j = math.floor((cell_y + p.width) * (p.rows - 1) / (2 * p.width))
        grid.h[k * p.rows + j + 1] = False
        self.assertIsNone(self.grid.height(grid, cell_x, cell_y))
        self.assertIsNone(self.grid.height(grid, p.lo - 0.01, 0))
        self.assertIsNone(self.grid.height(grid, 0, p.width + 0.01))

    def test_finer_rows_and_stations_capture_a_ridge_missed_by_the_old_grid(self):
        p = self.plan('strip', -100 / 3, 100 / 3, 10)
        ridge_x = p.lo + (p.hi - p.lo) * 7 / p.n
        ridge_y = p.row_offsets[4]

        def narrow_ridge(x, y):
            return 10 if abs(x - ridge_x) < 0.1 and abs(y - ridge_y) < 0.1 else 0

        grid = self.make_sampled_grid(p, narrow_ridge)
        self.assertAlmostEqual(self.grid.height(grid, ridge_x, ridge_y), 10, places=10)

        old_axial = [(-100 + 10 * k) for k in range(21)]
        old_lateral = [-10.5, 0, 10.5]
        self.assertNotIn(ridge_x, old_axial)
        self.assertNotIn(ridge_y, old_lateral)
        self.assertEqual(max(narrow_ridge(x, y)
                             for x in old_axial for y in old_lateral), 0)

    def station_values(self, stations):
        return [stations[i] for i in range(1, len(stations) + 1)]

    def test_short_strip_stations_include_display_edges_and_every_inner_sample(self):
        p = self.plan('strip', -100 / 3, 100 / 3, 10)
        stations = self.station_values(self.grid.stations(p, -100 / 3, 100 / 3))
        expected = [-100 / 3]
        expected.extend(p.lo + (p.hi - p.lo) * k / p.n for k in range(1, p.n))
        expected.append(100 / 3)
        self.assertEqual(len(stations), len(expected))
        for actual, want in zip(stations, expected):
            self.assertAlmostEqual(actual, want, places=10)

    def test_asymmetric_strafe_range_is_clipped_without_extrapolation(self):
        p = self.plan('strip', -5, 55, 5)
        stations = self.station_values(self.grid.stations(p, -5, 55))
        self.assertEqual(stations[0], -5)
        self.assertEqual(stations[-1], 55)
        self.assertTrue(all(-5 <= value <= 55 for value in stations))
        self.assertEqual(len(stations), 11)

    def test_circle_and_long_direction_keep_interior_grid_stations(self):
        circle = self.plan('circle', -25, 25, 25, 25)
        circular = self.station_values(self.grid.stations(circle, -25, 25))
        self.assertAlmostEqual(circular[0], -25)
        self.assertAlmostEqual(circular[-1], 25)
        self.assertEqual(len(circular), 9)

        long = self.plan('direction', -100, 100, 6)
        axial = self.station_values(self.grid.stations(long, -100, 100))
        self.assertAlmostEqual(axial[0], -100)
        self.assertAlmostEqual(axial[-1], 100)
        self.assertEqual(len(axial), 25)

    def test_endpoint_coincidence_is_deduplicated_and_invalid_ranges_fail_closed(self):
        p = self.plan('strip', -20, 20, 5)
        coincident = self.station_values(self.grid.stations(p, p.lo, p.hi))
        self.assertEqual(len(coincident), p.n + 1)
        self.assertEqual(coincident[0], p.lo)
        self.assertEqual(coincident[-1], p.hi)
        self.assertIsNone(self.grid.stations(p, p.lo - 1, p.hi))
        self.assertIsNone(self.grid.stations(p, 2, 1))
        self.assertIsNone(self.grid.stations(None, 0, 1))
        self.assertIsNone(self.grid.stations(p, float('nan'), 1))

    def test_display_stations_retain_a_midpoint_peak_missed_by_legacy_ten_m_mesh(self):
        lo, hi = -32, 32
        p = self.plan('strip', lo, hi, 10)
        stations = self.station_values(self.grid.stations(p, lo, hi))
        peak = p.lo + (p.hi - p.lo) * 5 / p.n
        legacy_steps = math.ceil((hi - lo) / 10)
        legacy = [lo + (hi - lo) * k / legacy_steps for k in range(legacy_steps + 1)]
        self.assertAlmostEqual(peak, 0, places=10)
        self.assertIn(peak, stations)
        self.assertTrue(all(abs(value - peak) > 0.1 for value in legacy))

    def test_bound_sampler_matches_height_and_reads_later_cached_hits(self):
        p = self.plan('strip', -20, 20, 6)
        grid = self.make_sampled_grid(p, lambda x, y: 0.5 * x - 2 * y + 9)
        sampler = self.grid.bind(grid)
        self.assertTrue(callable(sampler))
        for x, y in ((-19.5, -6), (-7.25, 1.4), (0, 0), (19.5, 5.5)):
            self.assertAlmostEqual(sampler(x, y), self.grid.height(grid, x, y), places=10)

        grid.h[0 * p.rows + 2] = False
        self.assertIsNone(sampler(p.lo, p.row_offsets[2]))
        grid.h[0 * p.rows + 2] = 42
        self.assertEqual(sampler(p.lo, p.row_offsets[2]), 42)

    def test_bound_sampler_preserves_domain_and_metadata_validation(self):
        p = self.plan('circle', -25, 25, 25, 25)
        grid = self.make_sampled_grid(p, lambda x, y: 3)
        sampler = self.grid.bind(grid)
        self.assertEqual(sampler(p.lo, -p.width), 3)
        self.assertIsNone(sampler(p.lo - 0.01, 0))
        self.assertIsNone(sampler(0, p.width + 0.01))
        self.assertIsNone(self.grid.bind(None))
        self.assertIsNone(self.grid.bind(self.lua.table_from({
            'lo': 0, 'hi': 1, 'width': 1, 'n': 1, 'rows': 2,
        })))

    def test_bound_sampler_uses_the_height_table_captured_at_bind_time(self):
        p = self.plan('strip', -10, 10, 4)
        grid = self.make_sampled_grid(p, lambda x, y: 1)
        sampler = self.grid.bind(grid)
        old_heights = grid.h
        replacement = self.lua.table()
        grid.h = replacement
        self.assertEqual(sampler(0, 0), 1)
        replacement[1] = 99
        self.assertEqual(sampler(0, 0), 1)
        grid.h = old_heights
        replacement_sampler = self.grid.bind(grid)
        self.assertEqual(replacement_sampler(0, 0), 1)


if __name__ == '__main__':
    unittest.main()
