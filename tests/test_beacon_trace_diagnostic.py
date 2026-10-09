"""Beacon trace fields are attached to the existing settled-beacon replay."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lupa.luajit21 import LuaError, LuaRuntime

from test_mission_feedback import REPO, SETUP, THROW


class BeaconTraceDiagnosticTest(unittest.TestCase):
    def test_landed_beacon_has_trace_id_in_log_and_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "CowboyBingus/Helldivers2/Logs"
            logs.mkdir(parents=True)
            with patch.dict(os.environ, {
                "DSH_HARNESS_TMP": tmp,
                "DSH_PROBE_PATH": str(REPO / "src/eagle_direction_probe.lua"),
                "DSH_HARNESS_MODE": "normal",
                "DSH_FRAME_DT": "0.05",
            }):
                lua = LuaRuntime()
                lua.execute("print=function() end")
                try:
                    lua.execute(SETUP + THROW + r'''
local strike=next(M.impacts)
ST.beacon_arc=1;tick(10)
assert(M.impacts[strike]==nil,'bounce must withdraw the provisional impact')
ST.beacon_arc=5;tick(20)
assert(M.impacts[strike]~=nil,'same handle must re-land under the same strike')
tick(40)
''')
                except LuaError as error:
                    excerpt = (logs / "EagleDirectionProbe.log").read_text(encoding="utf-8")
                    raise AssertionError(str(error) + "\n" + excerpt) from error
                finally:
                    if lua.globals().shutdown:
                        lua.globals().shutdown()
            log = (logs / "EagleDirectionProbe.log").read_text(encoding="utf-8")
            records = [json.loads(line) for path in logs.glob("*.jsonl")
                       for line in path.read_text(encoding="utf-8").splitlines()]
        trace_lines = [line for line in log.splitlines() if "beacon B" in line]
        self.assertTrue(any("B1 throw" in line for line in trace_lines), log)
        self.assertTrue(any("B1 call-bound" in line and "call=1" in line
                            for line in trace_lines), log)
        self.assertTrue(any("B1" in line and "landed" in line for line in trace_lines), log)
        withdraw = next((line for line in trace_lines if "B1 withdraw" in line), "")
        self.assertIn("p=12.0,8.0,38.0", withdraw, trace_lines)
        self.assertIn("call=1", withdraw)
        self.assertEqual(len(trace_lines), 5, trace_lines)
        self.assertEqual({line.split("beacon ", 1)[1].split()[0] for line in trace_lines},
                         {"B1"}, trace_lines)
        points = [point for record in records if record.get("kind") == "sample"
                  for point in record.get("beacons", [])]
        beacon_points = [point for point in points if point.get("id") == "16f397ca5f51f271"]
        self.assertTrue(any(point.get("trace") == 1 and point.get("motion") == "settled"
                            for point in beacon_points), log)

if __name__ == "__main__":
    unittest.main()
