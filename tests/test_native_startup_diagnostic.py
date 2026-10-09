"""Startup binding snapshot is passive and emitted once even on the ship."""
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lupa.luajit21 import LuaRuntime

from test_mission_feedback import SETUP

REPO = Path(__file__).resolve().parents[1]
SOURCE = (REPO / "src/eagle_direction_probe.lua").read_text(encoding="utf-8")
VERSION = re.search(r"version = '([^']+)'", SOURCE).group(1)


class NativeStartupDiagnosticTest(unittest.TestCase):
    def run_menu(self, pre_load="", frames=8):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "CowboyBingus/Helldivers2/Logs").mkdir(parents=True)
            setup = SETUP.replace(
                "local chunk, err = loadfile(probe_path)",
                r'''
local real_open=io.open
_G.fixture_handles={}
io.open=function(...)
    local f,e=real_open(...)
    if f then _G.fixture_handles[#_G.fixture_handles+1]=f end
    return f,e
end
''' + pre_load + "\nlocal chunk, err = loadfile(probe_path)",
            )
            with patch.dict(os.environ, {
                "DSH_HARNESS_TMP": tmp,
                "DSH_PROBE_PATH": str(REPO / "src/eagle_direction_probe.lua"),
                "DSH_HARNESS_MODE": "normal",
                "DSH_FRAME_DT": "0.05",
            }):
                lua = LuaRuntime()
                lua.execute("print = function() end")
                lua.execute(setup)
                for _ in range(frames):
                    lua.globals().update()
                state = lua.globals().HD2EagleDirectionProbe
                assert state.show_native_light_probe is False
                assert state.native_light_probe is None
                assert lua.eval("next(HD2EagleDirectionProbe.impacts) == nil")
                forbidden = lua.globals().forbidden_calls or 0
                terrain_calls = state.terrain_queries or 0
                update_unchanged = lua.eval("fixture_update == nil or update == fixture_update")
                if lua.globals().shutdown:
                    lua.globals().shutdown()
            log = Path(tmp) / "CowboyBingus/Helldivers2/Logs/EagleDirectionProbe.log"
            contents = log.read_text(encoding="utf-8")
            lua.execute("for _,f in ipairs(fixture_handles) do pcall(f.close,f) end")
            return contents, forbidden, terrain_calls, update_unchanged

    def test_snapshot_logs_api_types_once_without_world_or_native_light_calls(self):
        log = self.run_menu(pre_load=r'''
_G.forbidden_calls=0
for _,name in ipairs({'set_enabled','set_color','set_intensity','color','intensity',
    'get_color','get_intensity','set_spot_angle_end','set_falloff_end'}) do
    sr.Light=sr.Light or {}
    sr.Light[name]=function() _G.forbidden_calls=_G.forbidden_calls+1;error('diagnostic invoked Light API') end
end
sr.World.spawn_unit=function() _G.forbidden_calls=_G.forbidden_calls+1;error('diagnostic spawned helper') end
sr.World.update_unit=function() _G.forbidden_calls=_G.forbidden_calls+1;error('diagnostic updated unit') end
sr.World.destroy_unit=function() _G.forbidden_calls=_G.forbidden_calls+1;error('diagnostic destroyed unit') end
sr.Application.main_world=function() return nil end
sr.Application.worlds=function() return {} end
sr.GameSession.in_session=function() return false end
''')
        log, forbidden, terrain_calls, _ = log
        snapshots = [line for line in log.splitlines()
                     if "native-light capabilities" in line]
        self.assertEqual(len(snapshots), 1, log)
        line = snapshots[0]
        for field in (
            f"v{VERSION}",
            "Light.set_enabled=function", "Light.set_color=function",
            "Light.set_intensity=function", "Light.color=function",
            "Light.intensity=function", "Light.get_color=function",
            "Light.get_intensity=function", "Light.set_spot_angle_end=function",
            "Light.set_falloff_end=function", "World.spawn_unit=function",
            "World.update_unit=function", "World.destroy_unit=function",
            "Unit.node=nil", "Unit.light=nil", "Unit.num_lights=nil",
            "Unit.has_light=nil", "Unit.set_local_position=nil",
            "Unit.set_local_rotation=nil", "Unit.set_unit_visibility=nil",
            "Unit.alive=nil", "Quaternion.axis_angle=nil",
            "Vector3=table(callable=true)", "Vector3.x=function",
            "Vector3.y=function", "Vector3.z=function",
            "Application.worlds=function", "Application.can_get=nil",
        ):
            self.assertIn(field, line)
        self.assertNotIn("0x", line)
        self.assertNotIn("table: ", line)
        self.assertIn("no main world yet", log)  # still logs outside a mission/world
        self.assertEqual(forbidden, 0)
        self.assertEqual(terrain_calls, 0)

    def test_missing_namespace_is_reported_as_nil_and_snapshot_is_not_repeated(self):
        log, _, _, _ = self.run_menu(pre_load="sr.Light=nil", frames=20)
        snapshots = [line for line in log.splitlines()
                     if "native-light capabilities" in line]
        self.assertEqual(len(snapshots), 1, log)
        self.assertIn("Light=nil", snapshots[0])
        self.assertIn("Light.set_color=nil", snapshots[0])

    def test_missing_stingray_binding_is_reported_once_without_wrapping_update(self):
        log, _, _, update_unchanged = self.run_menu(
            pre_load="_G.fixture_update=update; _G.stingray=nil", frames=8)
        snapshots = [line for line in log.splitlines()
                     if "native-light capabilities" in line]
        self.assertEqual(len(snapshots), 1, log)
        self.assertIn("stingray=nil", snapshots[0])
        self.assertIn("Light.set_color=nil", snapshots[0])
        # Failed startup must not install an update wrapper just for diagnostics.
        # `run_menu` executes the global update repeatedly after the missing-binding return.
        self.assertTrue(update_unchanged)

    def test_false_api_field_and_protected_vector_metatable_are_not_misreported(self):
        log, _, _, _ = self.run_menu(pre_load=r'''
sr.Light={color=false}
local mt=getmetatable(sr.Vector3)
setmetatable(sr.Vector3,{__call=mt.__call,__metatable='protected-vector-metatable'})
''')
        snapshot = next(line for line in log.splitlines()
                        if "native-light capabilities" in line)
        self.assertIn("Light.color=boolean", snapshot)
        self.assertIn("Vector3=table(callable=unknown)", snapshot)


if __name__ == "__main__":
    unittest.main()
