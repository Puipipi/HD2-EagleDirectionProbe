"""Reproduce the player's report offline: how often is the corridor actually ON SCREEN?

The harness now models the thing it was missing - dispatch is per-frame, so a line object that is
not dispatched in a frame draws nothing in that frame.

That makes the field report testable. The player said: "a pair of white lines appeared for an
instant and then vanished, and nothing else." Every build they have played used submit-only-on-
geometry-change. This runs both modes through the same scenario and counts rendered frames.
"""
import os
import pathlib
import re
import tempfile

from lupa.luajit21 import LuaRuntime

ROOT = pathlib.Path(__file__).resolve().parents[2]      # mods/eagle-direction-probe
PROBE = ROOT / "src" / "eagle_direction_probe.lua"
HARNESS = pathlib.Path(__file__).resolve().parent / "harness_draw.lua"


def run(label, source, frame_dt):
    work = pathlib.Path(tempfile.mkdtemp(prefix="persist-"))
    path = work / "probe.lua"
    path.write_text(source, encoding="utf-8")
    tmp = tempfile.mkdtemp(prefix="persist-tmp-")
    os.makedirs(os.path.join(tmp, "CowboyBingus", "Helldivers2", "Logs"), exist_ok=True)
    os.environ["DSH_HARNESS_TMP"] = tmp
    os.environ["DSH_PROBE_PATH"] = str(path)
    os.environ["DSH_HARNESS_MODE"] = "normal"
    os.environ["DSH_FRAME_DT"] = str(frame_dt)
    src = HARNESS.read_text(encoding="utf-8")
    print("---- %s   (%.0f fps) ----" % (label, 1.0 / frame_dt))
    LuaRuntime(unpack_returned_tuples=True).execute(src)
    print()


original = PROBE.read_text(encoding="utf-8")
cheap = re.sub(r"every_frame = true,", "every_frame = false,", original)

# The game measured 133-156 fps in the captured sessions, with the corridor refreshing at 20 Hz.
for fps in (140.0, 60.0):
    run("SUBMIT EVERY FRAME (shipped default)", original, 1.0 / fps)
    run("SUBMIT ONLY ON CHANGE (every build the player has tried)", cheap, 1.0 / fps)
