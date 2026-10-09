"""Contract tests for the pure-Lua corridor label stroke font."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "src" / "cordon_font.lua"


class CordonFontTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime()
        cls.font = cls.lua.execute(
            "return assert(loadfile(...))()", str(MODULE)
        )

    def test_all_supported_glyphs_have_finite_nonzero_strokes(self):
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789?":
            strokes = self.font.get(char)
            self.assertIsNotNone(strokes, char)
            self.assertGreater(len(strokes), 0, char)
            for stroke in strokes.values():
                x0, y0, x1, y1 = (stroke[k] for k in ("x0", "y0", "x1", "y1"))
                self.assertTrue(all(map(lambda n: isinstance(n, (int, float)), (x0, y0, x1, y1))))
                self.assertTrue(all(map(lambda n: float("-inf") < n < float("inf"), (x0, y0, x1, y1))))
                self.assertTrue(all(0 <= n <= 1 for n in (x0, x1, y0, y1)))
                self.assertNotEqual((x0, y0), (x1, y1), (char, x0, y0, x1, y1))

    def test_letters_are_distinct_readable_vector_signatures(self):
        self.lua.globals().font = self.font
        self.lua.execute("""
            local function has(ch, predicate)
                for _,s in ipairs(font.get(ch)) do if predicate(s) then return true end end
                return false
            end
            -- A has a true diagonal and crossbar, R has a diagonal leg, G opens
            -- on the right and has a horizontal hook, and B is not a closed 8.
            assert(has('A',function(s) return s.x0~=s.x1 and math.max(s.y0,s.y1)==1 end), 'A diagonal')
            assert(has('A',function(s) return s.y0==s.y1 and s.y0>0 and s.y0<1 end), 'A crossbar')
            assert(has('R',function(s) return s.x0~=s.x1 and s.y0~=s.y1 end), 'R diagonal leg')
            assert(has('G',function(s) return s.y0==s.y1 and s.x0~=s.x1 end), 'G crossbar')
            assert(has('G',function(s) return math.min(s.x0,s.x1)>0 end), 'G open side')
            local function signature(ch)
                local out={}
                for _,s in ipairs(font.get(ch)) do
                    out[#out+1]=table.concat({s.x0,s.y0,s.x1,s.y1},',')
                end
                table.sort(out);return table.concat(out,';')
            end
            assert(signature('B')~=signature('8'), 'B and 8 must differ')
            assert(signature('O')~=signature('0'), 'O and 0 must differ')
            assert(signature('I')~=signature('1'), 'I and 1 must differ')
        """)

    def test_current_eagle_names_are_fully_supported(self):
        for name in ("NAPALM", "CLUSTER", "AIRSTRIKE", "SMOKE", "GAS", "STRAFE", "500KG", "110MM"):
            for char in name:
                if char != " ":
                    self.assertIsNotNone(self.font.get(char), (name, char))

    def test_lookup_is_cached_and_space_is_blank(self):
        self.lua.globals().font = self.font
        self.lua.execute("assert(font.get('A') == font.get('A')); assert(font.get(' ') == nil)")


if __name__ == "__main__":
    unittest.main()
