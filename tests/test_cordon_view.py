"""Pure side selection for single-view cordon lettering."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "src" / "cordon_view.lua"


class CordonViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime()
        cls.view = cls.lua.execute("return assert(loadfile(...))()", str(MODULE))
        cls.lua.globals().cordon_view = cls.view

    def choose(self, viewer, center, normal, last=None):
        def table(value):
            return None if value is None else self.lua.table_from(value)
        return self.view.choose(table(viewer), table(center), table(normal), last)

    def test_dot_side_selects_outer_or_inner_for_either_normal_direction(self):
        self.assertEqual(self.choose([0, 5, 0], [0, 0, 0], [0, 2, 0]), "outer")
        self.assertEqual(self.choose([0, -5, 0], [0, 0, 0], [0, 2, 0]), "inner")
        self.assertEqual(self.choose([0, -5, 0], [0, 0, 0], [0, -2, 0]), "outer")
        self.assertEqual(self.choose([0, 5, 0], [0, 0, 0], [0, -2, 0]), "inner")

    def test_circle_radial_normal_selects_only_the_facing_side(self):
        # At a quarter turn the radial panel normal points along +X.
        self.assertEqual(self.choose([12, 0, 0], [0, 0, 0], [3, 0, 0]), "outer")
        self.assertEqual(self.choose([-12, 0, 0], [0, 0, 0], [3, 0, 0]), "inner")

    def test_boundary_uses_hysteresis_or_one_deterministic_tie_side(self):
        self.assertEqual(self.choose([0, 0, 0], [0, 0, 0], [0, 1, 0], "inner"), "inner")
        self.assertEqual(self.choose([0, 0, 0], [0, 0, 0], [0, 1, 0]), "outer")
        self.assertEqual(self.choose([0, 0.01, 0], [0, 0, 0], [0, 1, 0], "inner"), "inner")
        self.assertEqual(self.choose([0, 0.10, 0], [0, 0, 0], [0, 1, 0], "inner"), "outer")
        self.assertEqual(self.choose([0, -0.10, 0], [0, 0, 0], [0, 1, 0], "outer"), "inner")

    def test_missing_viewer_preserves_only_a_valid_previous_side(self):
        self.assertEqual(self.choose(None, [0, 0, 0], [0, 1, 0], "inner"), "inner")
        self.assertEqual(self.choose(None, [0, 0, 0], [0, 1, 0]), None)
        self.assertEqual(self.choose(None, [0, 0, 0], [0, 1, 0], "both"), None)

    def test_invalid_or_nonfinite_vectors_return_unknown(self):
        self.assertIsNone(self.choose([0, 1], [0, 0, 0], [0, 1, 0]))
        self.assertIsNone(self.choose([0, 1, 0], [0, 0, 0], [0, 0, 0]))
        self.assertIsNone(self.choose([0, float("inf"), 0], [0, 0, 0], [0, 1, 0]))
        self.assertIsNone(self.choose([0, 1, 0], [0, 0, 0], [0, float("nan"), 0]))

    def test_selection_does_not_mutate_inputs(self):
        self.lua.globals().viewer = self.lua.table_from([3, 4, 0])
        self.lua.globals().center = self.lua.table_from([1, 1, 0])
        self.lua.globals().normal = self.lua.table_from([0, 2, 0])
        self.lua.execute("""
            local v,c,n=viewer[1]..','..viewer[2]..','..viewer[3],
                center[1]..','..center[2]..','..center[3],
                normal[1]..','..normal[2]..','..normal[3]
            assert(cordon_view.choose(viewer,center,normal)=='outer')
            assert(v==viewer[1]..','..viewer[2]..','..viewer[3])
            assert(c==center[1]..','..center[2]..','..center[3])
            assert(n==normal[1]..','..normal[2]..','..normal[3])
        """)


if __name__ == "__main__":
    unittest.main()
