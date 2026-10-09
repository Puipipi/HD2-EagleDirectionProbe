"""Pure outline extraction and dash segmentation for the depth-tested pass."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


MODULE = Path(__file__).resolve().parents[1] / 'src/occlusion_outline.lua'


class OcclusionOutlineTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        load = self.lua.eval("function(path) return assert(loadfile(path))() end")
        self.outline = load(str(MODULE))

    def batch(self, records):
        batch = self.lua.table()
        for i, record in enumerate(records, 1):
            batch[i] = record
        return batch

    def line(self, kind, a, b):
        return self.lua.table_from([kind, self.lua.table_from(a), self.lua.table_from(b)])

    def tri(self, kind, a, b, c):
        return self.lua.table_from([
            kind, self.lua.table_from(a), self.lua.table_from(b), self.lua.table_from(c),
        ])

    def test_quad_diagonal_is_removed_and_source_points_are_not_modified(self):
        a, b, c, d = ([0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0])
        records = self.batch([self.tri('area', a, b, c), self.tri('area', a, c, d)])
        lines = list(self.outline.build(records).values())
        self.assertEqual(len(lines), 4)
        self.assertEqual({line.kind for line in lines}, {'area'})
        edges = {frozenset(tuple(line[k][i] for i in range(1, 4)) for k in ('p1', 'p2'))
                 for line in lines}
        self.assertNotIn(frozenset({tuple(a), tuple(c)}), edges)
        self.assertEqual([records[1][2][i] for i in range(1, 4)], a)
        self.assertFalse(self.lua.eval('rawequal')(lines[1].p1, records[1][2]))

    def test_tessellated_adjacent_quads_remove_shared_edge_and_keep_outer_segments(self):
        a, b, c, d = ([0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0])
        e, f = ([2, 0, 0], [2, 1, 0])
        records = self.batch([
            self.tri('ground', a, b, c), self.tri('ground', a, c, d),
            self.tri('ground', b, e, f), self.tri('ground', b, f, c),
        ])
        lines = list(self.outline.build(records).values())
        self.assertEqual(len(lines), 6)
        shared = frozenset({tuple(b), tuple(c)})
        emitted = [frozenset(tuple(line[k][i] for i in range(1, 4))
                             for k in ('p1', 'p2')) for line in lines]
        self.assertNotIn(shared, emitted)

    def test_distinct_kinds_do_not_cancel_and_closed_marker_keeps_unique_wire_edges(self):
        a, b, c, d = ([0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1])
        tetra = [
            self.tri('marker', a, c, b), self.tri('marker', a, b, d),
            self.tri('marker', a, d, c), self.tri('marker', b, c, d),
        ]
        lines = list(self.outline.build(self.batch(tetra)).values())
        self.assertEqual(len(lines), 6)
        self.assertEqual(len({frozenset(tuple(line[k][i] for i in range(1, 4))
                                        for k in ('p1', 'p2')) for line in lines}), 6)

        separate = list(self.outline.build(self.batch([
            self.tri('ground', a, b, c), self.tri('area', a, b, c),
        ])).values())
        self.assertEqual(len(separate), 6)
        self.assertEqual({line.kind for line in separate}, {'ground', 'area'})

    def test_original_lines_survive_and_nearby_triangle_vertices_weld_with_tolerance(self):
        a, b, c, d = ([0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0])
        records = self.batch([
            self.tri('sky', a, b, c),
            self.tri('sky', [0.000004, 0, 0], [1, 1.000004, 0], d),
            self.line('cordon_text', [0, 0, 1], [0.4, 0, 1]),
        ])
        lines = list(self.outline.build(records).values())
        sky = [edge for edge in lines if edge.kind == 'sky']
        authored = [edge for edge in lines if edge.kind == 'cordon_text']
        self.assertEqual(len(sky), 4)
        self.assertEqual(len(authored), 1)
        self.assertFalse(sky[0].source_line)
        self.assertTrue(authored[0].source_line)
        self.assertAlmostEqual(authored[0].p2[1], 0.4)

    def test_welding_uses_coordinate_snap_bins_not_a_neighbor_radius_search(self):
        a, b, c, d = ([0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0])
        lines = list(self.outline.build(self.batch([
            self.tri('area', a, b, c),
            # These deltas are below 1e-5 m but cross the rounded-coordinate bin boundary.
            self.tri('area', [0.000006, 0, 0], [1.000006, 1, 0], d),
        ])).values())
        self.assertEqual(len(lines), 6)

    def test_invalid_and_zero_length_records_are_ignored(self):
        records = self.batch([
            self.line('cordon', [0, 0, 0], [0, 0, 0]),
            self.line('cordon', [0, 0, 0], [float('nan'), 1, 0]),
            self.lua.table_from(['area', self.lua.table_from([0, 0, 0])]),
            self.tri('area', [0, 0, 0], [1, 0, 0], [float('nan'), 1, 0]),
            self.tri('area', [0, 0, 0], [1, 0, 0], [2, 0, 0]),
        ])
        self.assertEqual(len(list(self.outline.build(records).values())), 0)

    def test_dash_splits_lines_without_fill_or_mutating_source_points(self):
        source = self.line('area', [0, 0, 0], [3, 0, 0])
        lines = list(self.outline.build(self.batch([source])).values())
        dashed = list(self.outline.dash(self.lua.table_from(lines), 1.2, 0.8).values())
        self.assertEqual(len(dashed), 2)
        self.assertEqual([(d.p1[1], d.p2[1]) for d in dashed], [(0, 1.2), (2, 3)])
        self.assertEqual([source[k][1] for k in (2, 3)], [0, 3])
        self.assertEqual([dashed[1].p1[2], dashed[1].p2[2]], [0, 0])
        self.assertTrue(all(d.p3 is None for d in dashed))

        short_lines = self.outline.build(self.batch([
            self.line('cordon_text', [4, 0, 0], [4.3, 0, 0]),
        ]))
        short = list(self.outline.dash(short_lines).values())
        self.assertEqual(len(short), 1)
        self.assertAlmostEqual(short[0].p2[1], 4.3)

    def test_invalid_dash_lengths_produce_no_segments(self):
        lines = self.outline.build(self.batch([self.line('area', [0, 0, 0], [2, 0, 0])]))
        self.assertEqual(len(self.outline.dash(lines, 0, 1)), 0)
        self.assertEqual(len(self.outline.dash(lines, 1, -1)), 0)


if __name__ == '__main__':
    unittest.main()
