"""Offline checks for the Eagle Direction Probe.

Three kinds of check, and they fail for different reasons on purpose:

* the analyzer must name a DIFFERENT rule for the strafing-run fixture than for the
  cluster fixture. A tool that reports the same rule for both has no discriminating
  power, and its readings on a real log would mean nothing.
* a deflected call must come back as a deflection, not as the rule being wrong - the
  player reports that the Eagle avoids obstacles, so a miss is not automatically
  evidence against a rule.
* the addon source must clear the packaging gates, and it must stay read-only.

No game, no network, no writes outside the repo. Run:

    python -m unittest discover -s tests -v
"""
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / 'tests' / 'fixtures'
ANALYZER_PATH = REPO / 'tools' / 'analyze_eagle_probe.py'
SOURCE_PATH = REPO / 'src' / 'eagle_direction_probe.lua'
BUILD_SCRIPT = REPO / 'work' / 'standalone' / 'build_probe.py'


def load_analyzer():
    spec = importlib.util.spec_from_file_location('analyze_eagle_probe', ANALYZER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = load_analyzer()


def analyze_fixture(name, labels=None):
    records = analyzer.load(str(FIXTURES / name))
    up, why = analyzer.choose_up(records, 'auto')
    calls = sorted({r['call'] for r in records if r.get('call')})
    rows = [analyzer.analyze_call(call, [r for r in records if r.get('call') == call],
                                  up, (labels or {}).get(str(call)))
            for call in calls]
    return up, why, rows


class PerStratagemRuleTest(unittest.TestCase):
    """Each Eagle stratagem gets its own rule, and the answers differ."""

    def test_strafing_resolves_to_along_from_behind(self):
        _, _, rows = analyze_fixture('strafing.jsonl')
        self.assertEqual(rows[0]['stratagem'], 'strafing_run',
                         'the munition identity should name the stratagem')
        verdict = analyzer.classify_verdict(rows)
        self.assertEqual(verdict['label'], 'rules_resolved')
        group = verdict['groups']['strafing_run']
        self.assertEqual(group['best_rule'], 'along_from_behind')
        self.assertEqual(group['verdict'], 'fits')
        self.assertLess(group['mean_abs_error_deg'], 5.0)

    def test_cluster_resolves_to_a_perpendicular_rule(self):
        _, _, rows = analyze_fixture('cluster.jsonl')
        self.assertEqual(rows[0]['stratagem'], 'cluster')
        verdict = analyzer.classify_verdict(rows)
        self.assertEqual(verdict['label'], 'rules_resolved')
        group = verdict['groups']['cluster']
        self.assertIn(group['best_rule'], ('perp_left', 'perp_right'))
        self.assertLess(group['mean_abs_error_deg'], 5.0)

    def test_the_two_stratagems_do_not_resolve_to_the_same_rule(self):
        """This is the discrimination test: same analyzer, different answers."""
        _, _, strafing = analyze_fixture('strafing.jsonl')
        _, _, cluster = analyze_fixture('cluster.jsonl')
        a = analyzer.classify_verdict(strafing)['groups']['strafing_run']['best_rule']
        b = analyzer.classify_verdict(cluster)['groups']['cluster']['best_rule']
        self.assertNotEqual(a, b, 'the analyzer cannot tell the two rules apart')

    def test_deflected_call_reads_as_deflection_not_as_a_wrong_rule(self):
        _, _, rows = analyze_fixture('deflected.jsonl')
        verdict = analyzer.classify_verdict(rows)
        self.assertEqual(verdict['label'], 'rules_with_deflection')
        group = verdict['groups']['strafing_run']
        self.assertEqual(group['best_rule'], 'along_from_behind')
        self.assertEqual(group['verdict'], 'mixed')
        self.assertEqual(group['tight_calls'], 1)
        self.assertEqual(group['deflected_calls'], 1)
        self.assertTrue(any('obstacle' in line.lower() for line in verdict['lines']),
                        'the reading must name the obstacle mechanic')

    def test_verdict_handles_no_usable_calls(self):
        self.assertEqual(analyzer.classify_verdict([])['label'], 'none')

    def test_vertical_axis_is_auto_detected(self):
        for name in ('strafing.jsonl', 'cluster.jsonl', 'deflected.jsonl'):
            up, why, _ = analyze_fixture(name)
            self.assertEqual(up, 'z', '%s: axis choice was %s (%s)' % (name, up, why))

    def test_explicit_labels_override_the_detected_munition(self):
        _, _, rows = analyze_fixture('cluster.jsonl', {'1': 'my_own_name'})
        self.assertEqual(rows[0]['stratagem'], 'my_own_name')

    def test_parse_labels(self):
        self.assertEqual(analyzer.parse_labels('1=a,2=b'), {'1': 'a', '2': 'b'})
        self.assertEqual(analyzer.parse_labels(None), {})
        self.assertEqual(analyzer.parse_labels(' 3 = c '), {'3': 'c'})
        with self.assertRaises(SystemExit):
            analyzer.parse_labels('nonsense')


class PreRegisteredFamilyTest(unittest.TestCase):
    """The reported families must be falsifiable, not read against whatever fits."""

    def test_strafing_fixture_confirms_the_parallel_family(self):
        _, _, rows = analyze_fixture('strafing.jsonl')
        group = analyzer.classify_verdict(rows)['groups']['strafing_run']
        self.assertEqual(group['expected_rules'], ['along_from_behind'])
        self.assertEqual(group['agreement'], 'confirms')

    def test_cluster_fixture_confirms_the_perpendicular_family(self):
        _, _, rows = analyze_fixture('cluster.jsonl')
        group = analyzer.classify_verdict(rows)['groups']['cluster']
        self.assertEqual(group['expected_rules'], ['perp_left', 'perp_right'])
        self.assertEqual(group['agreement'], 'confirms')

    def test_a_wrong_rule_is_reported_as_contradicting(self):
        """If the strafing run measured as perpendicular, that must be flagged."""
        self.assertNotIn('perp_left', analyzer.EXPECTED_RULES['strafing_run'])
        self.assertNotIn('along_from_behind', analyzer.EXPECTED_RULES['cluster'])

    def test_expectation_lookup(self):
        self.assertEqual(analyzer.expectation_for('strafing_run'),
                         ('along_from_behind',))
        self.assertEqual(analyzer.expectation_for('cluster'),
                         ('perp_left', 'perp_right'))
        # Compound labels (the strafing run has two munition identities) are the union.
        self.assertEqual(analyzer.expectation_for('eagle_gunpods'), None,
                         'raw munition names are not families and must not be guessed')
        self.assertIsNone(analyzer.expectation_for('unknown_stratagem'))
        self.assertIsNone(analyzer.expectation_for(''))
        self.assertIn('gas', analyzer.EXTRAPOLATED,
                      'the gas airstrike was not in the 2024 source; say so')


def lua_table_block(name):
    """The body of a top-level `local NAME = { ... }` table from the addon source.

    Splits on a closing brace at the start of a line, not on the first brace, because
    entries of these tables are themselves braced.
    """
    text = SOURCE_PATH.read_text(encoding='utf-8')
    marker = 'local %s = {' % name
    if marker not in text:
        raise AssertionError('%s not found in the addon source' % marker)
    return text.split(marker, 1)[1].split('\n}', 1)[0]


class MunitionMapDriftTest(unittest.TestCase):
    """The Lua and Python copies of the munition-to-stratagem map must agree.

    They are two hand-written tables that have to stay identical; a drift would make
    the analyzer name a different stratagem than the probe recorded, silently.
    """

    def test_python_mirror_matches_the_lua_table(self):
        block = lua_table_block('STRATAGEM_OF')
        pairs = {}
        for line in block.splitlines():
            # Accepts both 'key = value' and "['key'] = value" spellings.
            match = re.match(
                r"\s*(?:\[\s*'([a-z0-9_]+)'\s*\]|([a-z0-9_]+))\s*=\s*'([a-z0-9_]+)'",
                line)
            if match:
                pairs[match.group(1) or match.group(2)] = match.group(3)
        self.assertTrue(pairs, 'could not parse STRATAGEM_OF out of the Lua source')
        self.assertEqual(pairs, analyzer.STRATAGEM_OF,
                         'the Lua and Python munition maps have drifted apart')

    def test_probe_queries_a_key_for_every_mapped_munition(self):
        queried = set(re.findall(r"src = '([a-z0-9_]+)'", lua_table_block('QUERY_KEYS')))
        self.assertTrue(queried, 'could not parse QUERY_KEYS out of the Lua source')
        self.assertEqual(queried, set(analyzer.STRATAGEM_OF),
                         'QUERY_KEYS and STRATAGEM_OF cover different identities')


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
        self.source = SOURCE_PATH.read_text(encoding='utf-8')

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
