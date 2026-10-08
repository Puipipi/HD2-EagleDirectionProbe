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


class AircraftPreferenceTest(unittest.TestCase):
    """A munition track is a descent, not the incoming direction.

    The probe records the aircraft AND its munitions. A reader that simply took the
    longest track would measure a falling bomb, so this pins the preference.
    """

    def test_aircraft_is_chosen_over_a_longer_munition_track(self):
        _, _, rows = analyze_fixture('noisy.jsonl')
        row = rows[0]
        self.assertEqual(row['measured_from'], 'aircraft')
        self.assertNotIn('measured_from_warning', row)
        self.assertEqual(row['best_rule'], 'along_from_behind')

    def test_no_warning_when_every_call_used_the_aircraft(self):
        _, _, rows = analyze_fixture('noisy.jsonl')
        lines = ' '.join(analyzer.classify_verdict(rows)['lines'])
        self.assertNotIn('WARNING', lines)

    def test_munition_only_call_is_measured_but_flagged(self):
        _, _, rows = analyze_fixture('munition_only.jsonl')
        row = rows[0]
        self.assertNotEqual(row['measured_from'], 'aircraft')
        self.assertIn('measured_from_warning', row)
        lines = analyzer.classify_verdict(rows)['lines']
        self.assertTrue(any('WARNING' in line for line in lines),
                        'a fallback reading must be called out, not silently trusted')


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
    """The addon must not contain a write path. This is the whole safety claim.

    CHANGED DELIBERATELY in 0.7.0: this class used to forbid `LineObject.add_line`, because
    the addon drew nothing. It now draws the Eagle corridor, so that assertion had to be
    relaxed rather than deleted quietly. What replaces it is narrower and still meaningful:
    drawing may go through the LineObject API and NOTHING else, the GUI path stays banned,
    and every write call stays banned.
    """

    DRAW_API = ('sr.LineObject.reset', 'sr.LineObject.add_line', 'sr.LineObject.dispatch',
                'sr.World.create_line_object', 'sr.World.destroy_line_object')

    def setUp(self):
        self.source = SOURCE_PATH.read_text(encoding='utf-8')

    def test_no_engine_write_calls(self):
        for forbidden in ('Unit.set_local_position', 'Unit.set_local_rotation',
                          'Unit.set_local_scale', 'Material.set_vector',
                          'Material.set_scalar', 'spawn_unit', 'destroy_unit',
                          'Gui.triangle', 'Gui.rect', 'api.write',
                          'WriteProcessMemory'):
            self.assertNotIn(forbidden, self.source,
                             '%s appears in a no-write addon' % forbidden)

    def test_the_only_drawing_api_is_the_line_api(self):
        """Drawing is allowed now - but only through the API a running mod proved."""
        for call in self.DRAW_API:
            self.assertIn(call, self.source, '%s is the verified drawing path' % call)
        # Every draw call site must be one of the allowed ones: no other draw namespace.
        for forbidden in ('sr.Gui.', 'sr.Camera.draw', 'create_world_gui', 'sr.Material.'):
            self.assertNotIn(forbidden, self.source,
                             '%s is not part of the verified drawing path' % forbidden)

    def test_no_ffi_at_all(self):
        self.assertNotIn('ffi', self.source,
                         'this probe needs no FFI; keep it that way')

    def test_declares_read_only(self):
        self.assertIn('READ-ONLY', self.source)

    def test_drawing_has_an_escape_hatch(self):
        """The game has already been taken down twice; there is a switch with no rebuild.

        It is a FILE the player controls, checked at load and cheaply during the run, so
        turning the corridor off never depends on me shipping another version.
        """
        self.assertIn('EagleCorridor.off', self.source)
        self.assertIn('KILL_SWITCH', self.source)
        self.assertIn('drawing_allowed', self.source)

    def test_drawing_switches_itself_off_but_sampling_continues(self):
        """A slow or failing draw costs the corridor, not the measurement."""
        self.assertIn('DRAW_BUDGET_MS', self.source)
        self.assertIn('DRAW_SLOW_BEFORE_OFF', self.source)
        self.assertIn('corridor DISABLED: drawing was too slow', self.source)
        self.assertIn('corridor drawing ERRORED', self.source)

    def test_the_corridor_is_submitted_every_frame(self):
        """A dispatched line object is per-frame, so it cannot be submitted at 5 Hz.

        The geometry is recomputed at the sample rate; the submission is per frame. Both
        must happen inside the temp guard.
        """
        guard = self.source.split('local function guarded()', 1)[1].split('\nlocal ', 1)[0]
        self.assertIn('draw_corridor', guard,
                      'the draw must run in the per-frame path, not the sampled one')
        self.assertLess(guard.index('draw_corridor'), guard.index('temp_guard_end'),
                        'the draw must be inside the temp-byte-count guard')

    def test_the_per_frame_work_is_capped_by_construction(self):
        """The cost guarantee is deterministic, because it cannot be measured here.

        os.clock() has roughly 15.6 ms granularity on this engine - every engine query in
        this probe measures 0.0 ms against it - so the cap is a segment ceiling, not a
        timing promise.
        """
        self.assertIn('TRAIL_MAX', self.source)
        self.assertIn('if #trail > TRAIL_MAX then table.remove(trail, 1) end', self.source)

    def test_the_line_object_is_released(self):
        self.assertIn('release_line()', self.source)
        self.assertIn('sr.World.destroy_line_object', self.source)

    def test_the_drawing_self_test_is_opt_in_and_reports(self):
        """The riskiest new thing is the drawing path, and it must be provable without a mission.

        Waiting for an Eagle to test the line API would make a mission a dependency of a
        code check - so a file turns the test on and the log carries the verdict.
        """
        self.assertIn('EagleCorridor.selftest', self.source)
        self.assertIn('SELFTEST OK', self.source)
        self.assertIn('SELFTEST FAILED', self.source)
        self.assertIn('selftest_frames', self.source)

    def test_drawing_capability_is_proven_by_construction_not_by_type(self):
        """The first 0.7.0 run switched the corridor off because of a type test.

        sr.Vector3 is a callable table on this build and sr.Color is a function, so
        `type(...) == 'function'` rejected a working API. Capability must be established by
        actually constructing one, inside the temp guard, because constructing allocates in
        the script temp arena.
        """
        self.assertIn('pcall(sr.Vector3, 0, 0, 0)', self.source)
        self.assertIn('pcall(sr.Color, 255, 255, 255, 255)', self.source)
        self.assertIn('cap_saved', self.source)
        # The code form of the old check, not the mention of it in the comment that
        # explains the bug - a blunt substring test would fail on its own explanation.
        self.assertNotIn("and type(sr.Vector3) == 'function'", self.source)
        self.assertNotIn("and type(sr.Color) == 'function'", self.source)


class CostContractTest(unittest.TestCase):
    """The cost and safety rules 0.2.0 broke.

    0.2.0 queried 11 identities on every tick at 10 Hz and never restored the script
    temp byte count; the game then died with 0xC0000409 while the addon was sampling.
    These assertions exist so those two mistakes cannot come back quietly.
    """

    def setUp(self):
        self.source = SOURCE_PATH.read_text(encoding='utf-8')

    def sample_body(self):
        """The per-tick path only - the tick body, without the per-call pass."""
        marker = 'local function sample_body'
        self.assertIn(marker, self.source, 'sample_body is gone; update this test')
        body = self.source.split(marker, 1)[1]
        return body.split('local function guarded', 1)[0]

    def test_temp_byte_count_is_saved_and_restored(self):
        self.assertIn('temp_byte_count', self.source)
        self.assertIn('set_temp_byte_count', self.source)
        self.assertIn('temp_guard_begin', self.source)
        self.assertIn('temp_guard_end', self.source)

    def test_the_tick_is_wrapped_in_the_guard(self):
        guarded = self.source.split('local function guarded', 1)[1]
        self.assertIn('temp_guard_begin()', guarded)
        self.assertIn('temp_guard_end(', guarded)

    def test_per_tick_path_does_not_sweep_every_identity(self):
        body = self.sample_body()
        self.assertNotIn('RESOLVED', body,
                         'the per-tick path must not sweep the munition identities')
        calls = re.findall(r'units_by_resource\(([^()]*(?:\([^()]*\)[^()]*)*)\)', body)
        self.assertTrue(calls, 'no units_by_resource call found in the tick at all')
        self.assertLessEqual(len(calls), 4,
                             'the per-tick path must stay at the beacon plus aircraft')
        for args in calls:
            self.assertTrue('beacon_key()' in args or 'EAGLE_RESOURCE' in args,
                            'only the beacon and the aircraft may be queried per tick, '
                            'found: %s' % args)

    def test_sampling_is_gated_on_being_in_a_mission(self):
        self.assertIn('IN_SESSION_ONLY', self.source)
        self.assertIn('in_session()', self.source)
        body = self.sample_body()
        self.assertIn('in_session()', body,
                      'the mission gate must be inside the tick, before any query')

    def test_there_is_a_self_disable(self):
        self.assertIn('SELF-DISABLED', self.source)
        self.assertIn('SLOW_TICKS_BEFORE_STOP', self.source)
        self.assertIn('TICK_BUDGET_MS', self.source)

    def test_sample_rate_is_conservative(self):
        match = re.search(r'local SAMPLE_HZ\s*=\s*(\d+)', self.source)
        self.assertIsNotNone(match, 'SAMPLE_HZ is gone')
        self.assertLessEqual(int(match.group(1)), 5,
                             'the sample rate was raised; measure the cost first')

    def test_the_jsonl_is_flushed_periodically(self):
        self.assertIn('jsonl.flush', self.source,
                      'a crash must not cost us the data again')


    def test_in_session_is_called_with_its_session_argument(self):
        """0.3.0 called it bare and the game died with 0xC0000409.

        Every proven mod in this workspace writes `in_session(session)`, having got the
        session from `Network.game_session()` first. Inventing the signature instead of
        copying it is what killed the process, so it is pinned here.
        """
        self.assertIn('pcall(gs.in_session, session)', self.source,
                      'in_session must be called WITH the session argument')
        self.assertNotIn('pcall(gs.in_session)', self.source,
                         'the bare call is the 0.3.0 crash; do not bring it back')
        self.assertIn('net.game_session', self.source,
                      'the session must come from Network.game_session()')

    def test_there_is_a_startup_grace(self):
        self.assertIn('STARTUP_GRACE_S', self.source)
        self.assertRegex(self.source, r'STARTUP_GRACE_S\s*=\s*\d+')

    def test_a_stationary_beacon_does_not_count_as_a_call(self):
        """Neither presence nor drift may start a call - only a throw.

        0.2.0 inferred a call from the mere existence of a beacon-identity unit, and a
        stationary one sits on the ship - which is why it sampled in the loadout. The
        first captured mission then showed that several beacon-identity objects coexist
        and all log the same resource id, with the landed ones drifting tens of metres, so
        a displacement threshold fires on them too. Speed is the discriminator, and the
        object is tracked by its unit handle so the objects never mix.
        """
        self.assertIn('THROW_SPEED_MPS', self.source)
        self.assertIn('beacon_motion[entry.unit]', self.source,
                      'the motion table must be keyed by the unit handle')
        body = self.sample_body()
        self.assertIn('thrown ~= nil and active_call == nil', body,
                      'a call must require a throw, not presence or drift')

    def test_a_second_throw_splits_the_call(self):
        """Two throws must not be merged into one call.

        The timeout alone once swallowed a throw: five throws produced three calls when the
        timeout outlasted the gap between them. A different beacon flying fast is the
        signal that a new throw has begun.
        """
        body = self.sample_body()
        self.assertIn('primary_unit', body)
        self.assertIn('a different beacon was thrown', body,
                      'the call must be closed early when a new beacon is thrown')

    def test_the_thrown_beacon_is_marked_in_the_samples(self):
        """The analyzer cannot separate the objects without this flag.

        Several beacon-identity objects share one resource id, so the captured samples were
        unusable for the player-to-beacon line until the thrown one was marked.
        """
        self.assertIn('"primary":true', self.source,
                      'the thrown beacon must be marked in the samples')
        self.assertIn('entry.primary', self.source)

    def test_there_is_a_status_line_in_every_state(self):
        """A silent log must never again be ambiguous.

        Before this, waiting in the ship produced no lines at all, so "idle" and
        "reading nothing" looked identical.
        """
        self.assertIn('STATUS_S', self.source)
        self.assertIn("kind = 'status'", self.source)
        body = self.sample_body()
        self.assertIn('status:', body)

    def test_samples_are_written_to_a_per_session_file(self):
        """A relaunch must not destroy the previous session's samples.

        0.6.0 opened one fixed filename with 'w'. Merely starting the game again
        truncated a completed measurement - the log survived but holds counts, not
        coordinates, so the geometry was gone.
        """
        idx = self.source.find('local JSONL_PATH')
        self.assertNotEqual(idx, -1, 'JSONL_PATH is gone')
        window = self.source[idx:idx + 240]
        self.assertIn('os.time()', window,
                      'the samples filename must be unique per session')
        self.assertNotIn("'EagleDirectionProbe.jsonl'", self.source,
                         'the fixed filename is the truncation bug; do not bring it back')
        self.assertIn('samples file: ', self.source,
                      'the log must name the file, since the name changes now')

    def test_a_call_times_out_before_a_player_throws_again(self):
        """Five throws produced three calls because the timeout outlasted the gap.

        A call blocks new calls while it is active, so a timeout longer than the interval
        between throws swallows the next throw.
        """
        match = re.search(r'local CALL_TIMEOUT_S\s*=\s*(\d+)', self.source)
        self.assertIsNotNone(match, 'CALL_TIMEOUT_S is gone')
        self.assertLessEqual(int(match.group(1)), 10,
                             'a timeout this long will merge consecutive throws again')


if __name__ == '__main__':
    unittest.main()
