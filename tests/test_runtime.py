"""Execute shipped code on the game's LuaJIT, including its JSON output."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lupa.luajit21 import LuaError, LuaRuntime
from lupa.lua55 import LuaRuntime as Lua55Runtime

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / 'src' / 'eagle_direction_probe.lua'
HARNESS = REPO / 'tests' / 'offline' / 'harness_draw.lua'


class RuntimeRegressionTest(unittest.TestCase):
    def test_json_escapes_roundtrip_on_both_runtimes(self):
        source = SOURCE.read_text(encoding='utf-8')
        encoder = source.split('local JSON_ESC =', 1)[1].split('local function emit', 1)[0]
        for runtime in (LuaRuntime, Lua55Runtime):
            with self.subTest(runtime=runtime.__module__):
                lua = runtime(unpack_returned_tuples=True)
                encode = lua.execute('local JSON_ESC =' + encoder + '\nreturn json_string')
                value = ''.join(chr(i) for i in range(32)) + '"\\ 飞鹰'
                self.assertEqual(json.loads(encode(value)), value)

    def test_replay_writes_parseable_samples_without_lua_errors(self):
        for mode in ('normal', 'flaky', 'twoair'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                logs = Path(tmp) / 'CowboyBingus' / 'Helldivers2' / 'Logs'
                logs.mkdir(parents=True)
                env = {'DSH_HARNESS_TMP': tmp, 'DSH_PROBE_PATH': str(SOURCE),
                       'DSH_HARNESS_MODE': mode, 'DSH_FRAME_DT': str(1 / 140)}
                with patch.dict(os.environ, env):
                    lua = LuaRuntime(unpack_returned_tuples=True)
                    lua.execute('print = function() end')
                    lua.execute(HARNESS.read_text(encoding='utf-8'))
                    state = lua.globals().HD2EagleDirectionProbe
                    self.assertIsNotNone(state, 'replay must load the real source')
                    lua.globals().shutdown()
                    self.assertEqual(state.errors, 0, state.emit_error)
                    self.assertEqual(state.skipped or 0, 0,
                                     'ground segments must reach add_line with a valid colour')
                    self.assertGreater(lua.globals().GROUND_LINES_SUBMITTED or 0, 0,
                                       'creating a strip is insufficient: it must be submitted')
                    records = [json.loads(line) for p in logs.glob('*.jsonl')
                               for line in p.read_text(encoding='utf-8').splitlines()]
                    self.assertTrue(any(r['kind'] == 'sample' for r in records))
                    self.assertTrue(any(r.get('eagles') for r in records))

    def test_build_gate_rejects_syntax_unavailable_in_luajit(self):
        spec = importlib.util.spec_from_file_location(
            'eagle_build', REPO / 'work' / 'standalone' / 'build_probe.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        # Lua 5.4+ accepts <const>; the game's LuaJIT must reject it.
        with self.assertRaises(SystemExit):
            build.gate_luajit(b'local value <const> = 1; return value')

    def test_harness_runner_loads_source_and_fails_on_missing_source(self):
        runner = REPO / 'tests' / 'offline' / 'run_harness.py'
        result = subprocess.run([sys.executable, '-B', str(runner)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('LOAD FAILED', result.stdout)
        self.assertEqual(result.stdout.count('probe loaded:'), 4)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'DSH_HARNESS_TMP': tmp, 'DSH_PROBE_PATH': str(Path(tmp) / 'missing.lua')}):
            lua = LuaRuntime(unpack_returned_tuples=True)
            with self.assertRaises(LuaError):
                lua.execute(HARNESS.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
