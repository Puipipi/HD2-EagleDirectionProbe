"""Offline checks for the Eagle Direction Probe.

Two kinds of check, and they fail for different reasons on purpose:

* the analyzer must SEPARATE a case it should accept from one it should reject. A
  tool that reports "consistent" for both fixtures is not evidence, so the two
  synthetic fixtures disagree by construction and the test asserts they land far
  apart, not merely that one passes.
* the addon source must pass the packaging gates (LuaJIT compile, no user32 in
  ffi.cdef, declaration matches the resource name).

No game, no network, no writes outside the repo. Run:

    python -m unittest discover -s tests -v
"""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / 'tests' / 'fixtures'
ANALYZER_PATH = REPO / 'tools' / 'analyze_eagle_probe.py'
BUILD_SCRIPT = REPO / 'work' / 'standalone' / 'build_probe.py'


def load_analyzer():
    spec = importlib.util.spec_from_file_location('analyze_eagle_probe', ANALYZER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = load_analyzer()


def analyze_fixture(name):
    records = analyzer.load(str(FIXTURES / name))
    up, why = analyzer.choose_up(records, 'auto')
    calls = sorted({r['call'] for r in records if r.get('call')})
    rows = [analyzer.analyze_call(call, [r for r in records if r.get('call') == call], up)
            for call in calls]
    return up, why, rows


class AnalyzerDiscriminationTest(unittest.TestCase):
    """The analyzer must accept H1-shaped data and reject non-H1-shaped data."""

    def test_h1_fixture_is_accepted(self):
        up, _, rows = analyze_fixture('h1.jsonl')
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn('measured_axis_deg', row)
        self.assertTrue(row['h1_axis_matches'],
                        'H1 fixture should match, error was %s' % row.get('h1_error_best_deg'))
        self.assertLess(row['h1_error_best_deg'], 5.0)

    def test_h2_fixture_is_rejected(self):
        _, _, rows = analyze_fixture('h2.jsonl')
        row = rows[0]
        self.assertIn('measured_axis_deg', row)
        self.assertFalse(row['h1_axis_matches'],
                         'h2 fixture must NOT be reported as an H1 match')
        self.assertGreater(row['h1_error_best_deg'], 60.0)

    def test_the_two_fixtures_are_far_apart(self):
        """Guards against a regression that makes every input look like a match."""
        _, _, h1 = analyze_fixture('h1.jsonl')
        _, _, h2 = analyze_fixture('h2.jsonl')
        separation = abs(h2[0]['h1_error_best_deg'] - h1[0]['h1_error_best_deg'])
        self.assertGreater(separation, 60.0,
                           'the analyzer no longer separates accept from reject')

    def test_vertical_axis_is_auto_detected(self):
        for name in ('h1.jsonl', 'h2.jsonl'):
            up, why, _ = analyze_fixture(name)
            self.assertEqual(up, 'z', '%s: axis choice was %s (%s)' % (name, up, why))


class SourceGateTest(unittest.TestCase):
    """The source must clear the packaging gates before anything is built."""

    def test_source_gates_pass(self):
        result = subprocess.run(
            [sys.executable, '-B', str(BUILD_SCRIPT), '--validate-only'],
            capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(result.returncode, 0,
                         'gates failed:\n%s\n%s' % (result.stdout, result.stderr))
        self.assertIn('gate 1 ok: LuaJIT 2.1 compile', result.stdout)
        self.assertIn('gate 2 ok: no user32', result.stdout)
        self.assertIn('gate 3 ok: declaration matches', result.stdout)
        self.assertIn('validate-only', result.stdout)


class ReadOnlyContractTest(unittest.TestCase):
    """The addon must not contain a write path. This is the whole safety claim."""

    def setUp(self):
        self.source = (REPO / 'src' / 'eagle_direction_probe.lua').read_text(encoding='utf-8')

    def test_no_engine_write_calls(self):
        for forbidden in ('Unit.set_local_position', 'Unit.set_local_rotation',
                          'Unit.set_local_scale', 'Material.set_vector',
                          'Material.set_scalar', 'spawn_unit', 'destroy_unit',
                          'LineObject.add_line', 'Gui.triangle', 'api.write',
                          'WriteProcessMemory'):
            self.assertNotIn(forbidden, self.source,
                             '%s appears in a read-only probe' % forbidden)

    def test_no_ffi_at_all(self):
        self.assertNotIn('ffi', self.source,
                         'this probe needs no FFI; keep it that way')

    def test_declares_read_only(self):
        self.assertIn('READ-ONLY', self.source)


if __name__ == '__main__':
    unittest.main()
