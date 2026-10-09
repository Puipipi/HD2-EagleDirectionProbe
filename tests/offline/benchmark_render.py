"""Compare real Lua update work with a cheap fake native renderer, never game FPS.

Usage: python -B tests/offline/benchmark_render.py --baseline-ref v1.9.7
"""
import argparse
import json
import os
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from lupa.luajit21 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
SETUP = (ROOT/'tests/offline/harness_draw.lua').read_text(encoding='utf-8').split(
    "tick(30)\nreport('on the ship')", 1)[0]
SCENE = '''
-- Instrument only the native boundary; no retained ADDED/COLORS tables from the harness.
local lines=0
local faces,face_updates=0,0
if BENCH_SOLID then
    sr.Matrix4x4.identity=function() return {} end
    sr.World.create_world_gui=function() return {} end
    sr.World.destroy_gui=function() end
    sr.Gui.triangle=function() faces=faces+1;return faces end
    sr.Gui.update_triangle=function() face_updates=face_updates+1 end
    sr.Gui.destroy_triangle=function() end
    package.preload['mods/codex/eagle_solid_renderer']=function()
        return assert(loadfile(BENCH_RENDERER))()
    end
end
sr.LineObject.reset=function() end
sr.LineObject.add_line=function() lines=lines+1 end
sr.LineObject.dispatch=function() end
sr.Color=function(a,r,g,b) return {a=a,r=r,g=g,b=b} end
package.preload['mods/codex/eagle_terrain_query']=function()
    return {new=function() return {height=function(_,_,_,_,x,y,z) return z,'HIT' end} end}
end
M.tracks,M.track_order,M.impacts={},{},{}
for i=1,BENCH_STRIKES do
    M.tracks[i]={trail={{i*300,0,80}},heading={1,0,0},seen=FAKE_TIME+1000}
    M.track_order[i]=i
    M.impacts[i]={p={i*300,0,0},heading={1,0,0},beacon=BEACON,
        last_seen=FAKE_TIME+1000,t=FAKE_TIME}
end
local function step(n)
    for frame=1,n do
        FAKE_TIME=FAKE_TIME+1/140
        if frame%7==0 then -- 20 Hz aircraft sampling on a 140 Hz rendering loop
            for i,track in pairs(M.tracks) do
                track.trail={{i*300+(FAKE_TIME%10)*30,0,80}}
            end
        end
        update()
    end
end
step(600) -- all coarse grids completed and JIT warmed
assert(M.errors==0 and not M.draw_off,'invalid benchmark fixture')
collectgarbage('collect')
collectgarbage('stop') -- report allocated memory, separate from GC scheduling
local kb=collectgarbage('count')
local builds=M.ground_builds or 0
local queries=M.terrain_queries or 0
lines=0;face_updates=0
local face_creates=faces
BENCH_STEP=function(n)
    step(n)
    BENCH_KB=collectgarbage('count')-kb
    BENCH_LINES=lines
    BENCH_FACE_UPDATES=face_updates
    BENCH_FACE_CREATES=faces-face_creates
    BENCH_ACTIVE_FACES=M.solid_triangles or 0
    BENCH_SOLID_ACTIVE=M.solid_active or false
    BENCH_GROUND_BUILDS=(M.ground_builds or 0)-builds
    BENCH_QUERIES=(M.terrain_queries or 0)-queries
    assert(M.errors==0 and not M.draw_off,'benchmark update failed')
    collectgarbage('restart')
end
'''


def measure(path, strikes, frames, solid=False):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp)/'CowboyBingus/Helldivers2/Logs').mkdir(parents=True)
        with patch.dict(os.environ, {'DSH_HARNESS_TMP': tmp, 'DSH_PROBE_PATH': str(path),
                        'DSH_HARNESS_MODE': 'normal', 'DSH_FRAME_DT': '0.05'}):
            lua=LuaRuntime()
            lua.globals().BENCH_STRIKES=strikes
            lua.globals().BENCH_SOLID=solid
            lua.globals().BENCH_RENDERER=str(ROOT/'src/solid_renderer.lua')
            lua.execute('print=function() end')
            lua.execute(SETUP+SCENE)
            began=time.perf_counter()
            lua.globals().BENCH_STEP(frames)
            ms=(time.perf_counter()-began)*1000/frames
            g=lua.globals()
            row={'ms_per_frame':ms,'allocated_kb_per_frame':g.BENCH_KB/frames,
                 'lines_per_frame':g.BENCH_LINES/frames,
                 'face_updates_per_frame':g.BENCH_FACE_UPDATES/frames,
                 'face_creates':g.BENCH_FACE_CREATES,'active_faces':g.BENCH_ACTIVE_FACES,
                 'solid_active':bool(g.BENCH_SOLID_ACTIVE),
                 'ground_rebuilds':g.BENCH_GROUND_BUILDS,'terrain_queries':g.BENCH_QUERIES}
            lua.globals().shutdown()
            return row


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--baseline-ref',default='v1.9.7')
    ap.add_argument('--frames',type=int,default=280)
    ap.add_argument('--repeats',type=int,default=5)
    ap.add_argument('--solid-fill',action='store_true',help='exercise the real retained renderer with mock native APIs')
    args=ap.parse_args()
    baseline=subprocess.run(['git','show',args.baseline_ref+':src/eagle_direction_probe.lua'],
                            cwd=ROOT,capture_output=True,check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        old=Path(tmp)/'baseline.lua';old.write_bytes(baseline)
        result={'note':'Offline Lua CPU/allocation only; native renderer is fake, not game FPS.',
                'baseline':args.baseline_ref,'frames':args.frames,'repeats':args.repeats,'scenes':{}}
        for n in (1,4,8):
            rows={'baseline':[],'current':[]}
            # Alternate runs so warmup/thermal scheduling affects both versions similarly.
            for _ in range(args.repeats):
                for key,path in (('baseline',old),('current',ROOT/'src/eagle_direction_probe.lua')):
                    rows[key].append(measure(path,n,args.frames,args.solid_fill))
            result['scenes'][n]={key:{metric:round(statistics.median(r[metric] for r in runs),4)
                                for metric in runs[0]} for key,runs in rows.items()}
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
