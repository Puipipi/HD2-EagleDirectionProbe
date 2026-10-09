"""Compare real Lua update work with a cheap fake native renderer, never game FPS.

Usage: python -B tests/offline/benchmark_render.py --baseline-ref v1.9.7
       python -B tests/offline/benchmark_render.py --baseline-dir ../work/eagle-rc14-baseline
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
-- Let the real update initialize the current world epoch before seeding synthetic guides.
local lines=0
local faces,face_updates=0,0
local vector_calls,color_calls=0,0
local vector=sr.Vector3
sr.Vector3=setmetatable({}, {__index=vector,__call=function(_,...)
    vector_calls=vector_calls+1;return vector(...) end})
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
if BENCH_TYPES then
    package.preload['mods/codex/eagle_stratagem_profiles']=function()
        return assert(loadfile(BENCH_PROFILES))()
    end
    local records={}
    for i=1,BENCH_STRIKES do records[i]={type=BENCH_TYPE_ID,p={i*300,0,0}} end
    package.preload['mods/codex/eagle_stratagem_query']=function()
        return {new=function() return {snapshot=function() return records,'READY','bench' end} end}
    end
end
sr.LineObject.reset=function() end
sr.LineObject.add_line=function() lines=lines+1 end
sr.LineObject.dispatch=function() end
sr.Color=function(a,r,g,b) color_calls=color_calls+1;return {a=a,r=r,g=g,b=b} end
package.preload['mods/codex/eagle_terrain_query']=function()
    return {new=function() return {height=function(_,_,_,_,x,y,z) return z,'HIT' end} end}
end
-- Initialize world identity only after all renderer APIs have been installed, then seed.
-- This keeps the first synthetic guide in the same world epoch without prematurely disabling
-- true fill because the GUI mock was not yet available.
update()
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
if BENCH_THROUGH then
    -- Measure the first through-world frame separately so outline generation and retained
    -- geometry rebuild spikes remain visible instead of disappearing into warmup.
    M.through_world=true
    M.geom_key,M.flow_key,M.ground_geom_key=nil,nil,nil
end
BENCH_COLD_STEP=function() step(1) end
BENCH_WARMUP=function() step(599) end -- one separately timed cold frame + 599 warmup frames
BENCH_FINALIZE=function()
assert(M.errors==0 and not M.draw_off,'invalid benchmark fixture: errors='
    ..tostring(M.errors)..' draw_off='..tostring(M.draw_off)
    ..' error='..tostring(M.draw_error or M.trail_error))
local track_count,impact_count,confirmed_count=0,0,0
for _ in pairs(M.tracks) do track_count=track_count+1 end
for _,imp in pairs(M.impacts) do
    impact_count=impact_count+1
    if not BENCH_TYPES or imp.type_heading_confirmed then confirmed_count=confirmed_count+1 end
end
assert(track_count==BENCH_STRIKES and impact_count==BENCH_STRIKES
    and confirmed_count==BENCH_STRIKES,'benchmark did not retain all confirmed guides')
if BENCH_EXPECT_SOLID then
    assert(M.solid_active and (M.solid_triangles or 0)>0,'solid benchmark rendered no faces active='
        ..tostring(M.solid_active)..' faces='..tostring(M.solid_triangles)
        ..' status='..tostring(M.solid_status)..' failed='..tostring(M.solid_failed)
        ..' enabled='..tostring(M.draw_enabled)..' seg='..tostring(M.seg_count)
        ..' fill='..tostring(M.solid_fill)..' checked='..tostring(M.solid_checked)
        ..' tracks='..tostring(#M.track_order)..' impacts='..tostring(next(M.impacts))
        ..' showair='..tostring(M.show_air)..' through='..tostring(M.through_world)
        ..' line='..tostring(M.line)..' drawframes='..tostring(M.draw_frames)
        ..' selftest='..tostring(M.selftest))
elseif BENCH_SOLID then
    assert((M.seg_count or 0)>0,'line benchmark rendered no segments')
else
    assert((M.seg_count or 0)>0,'line benchmark rendered no segments')
end
collectgarbage('collect')
collectgarbage('stop') -- report allocated memory, separate from GC scheduling
local kb=collectgarbage('count')
local builds=M.ground_builds or 0
local queries=M.terrain_queries or 0
local type_reads=M.type_reads or 0
local outline_builds=OUTLINE_BUILDS or 0
local outline_dashes=OUTLINE_DASHES or 0
lines=0;face_updates=0;vector_calls=0;color_calls=0
local face_creates=faces
BENCH_STEP=function(n)
    step(n)
    BENCH_KB=collectgarbage('count')-kb
    BENCH_LINES=lines
    BENCH_FACE_UPDATES=face_updates
    BENCH_VECTOR_CALLS=vector_calls
    BENCH_COLOR_CALLS=color_calls
    BENCH_FACE_CREATES=faces-face_creates
    BENCH_ACTIVE_FACES=M.solid_triangles or 0
    BENCH_SOLID_ACTIVE=M.solid_active or false
    BENCH_GROUND_BUILDS=(M.ground_builds or 0)-builds
    BENCH_QUERIES=(M.terrain_queries or 0)-queries
    BENCH_TYPE_READS=(M.type_reads or 0)-type_reads
    BENCH_OUTLINE_BUILDS=(OUTLINE_BUILDS or 0)-outline_builds
    BENCH_OUTLINE_DASHES=(OUTLINE_DASHES or 0)-outline_dashes
    assert(M.errors==0 and not M.draw_off,'benchmark update failed')
    assert(BENCH_QUERIES==0,'benchmark unexpectedly issued a terrain query')
    collectgarbage('restart')
end
end
'''


def measure(path, strikes, frames, solid=False, types=False, type_id=18, renderer=None,
            profiles=None, through=False, expect_solid=True):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp)/'CowboyBingus/Helldivers2/Logs').mkdir(parents=True)
        with patch.dict(os.environ, {'DSH_HARNESS_TMP': tmp, 'DSH_PROBE_PATH': str(path),
                        'DSH_HARNESS_MODE': 'normal', 'DSH_FRAME_DT': '0.05'}):
            lua=LuaRuntime()
            lua.globals().BENCH_STRIKES=strikes
            lua.globals().BENCH_SOLID=solid
            lua.globals().BENCH_EXPECT_SOLID=expect_solid
            lua.globals().BENCH_RENDERER=str(renderer or ROOT/'src/solid_renderer.lua')
            lua.globals().BENCH_TYPES=types
            lua.globals().BENCH_THROUGH=through
            lua.globals().BENCH_TYPE_ID=type_id
            lua.globals().BENCH_PROFILES=str(profiles or ROOT/'src/stratagem_profiles.lua')
            try:
                lua.execute('print=function() end')
                lua.execute(SETUP+SCENE)
                cold_started=time.perf_counter()
                lua.globals().BENCH_COLD_STEP()
                cold_ms=(time.perf_counter()-cold_started)*1000
                g=lua.globals()
                cold_builds=int(g.OUTLINE_BUILDS or 0)
                cold_dashes=int(g.OUTLINE_DASHES or 0)
                lua.globals().BENCH_WARMUP()
                lua.globals().BENCH_FINALIZE()
                began=time.perf_counter()
                lua.globals().BENCH_STEP(frames)
                ms=(time.perf_counter()-began)*1000/frames
                row={'cold_first_frame_ms':cold_ms,
                     'cold_outline_builds':cold_builds,'cold_outline_dashes':cold_dashes,
                     'ms_per_frame':ms,'allocated_kb_per_frame':g.BENCH_KB/frames,
                     'lines_per_frame':g.BENCH_LINES/frames,
                     'face_updates_per_frame':g.BENCH_FACE_UPDATES/frames,
                     'vectors_per_frame':g.BENCH_VECTOR_CALLS/frames,
                     'colors_per_frame':g.BENCH_COLOR_CALLS/frames,
                     'face_creates':g.BENCH_FACE_CREATES,'active_faces':g.BENCH_ACTIVE_FACES,
                     'solid_active':bool(g.BENCH_SOLID_ACTIVE),
                     'retained_guides':g.BENCH_STRIKES,
                     'type_snapshots':g.BENCH_TYPE_READS,
                     'outline_builds':g.BENCH_OUTLINE_BUILDS,
                     'outline_dashes':g.BENCH_OUTLINE_DASHES,
                     'ground_rebuilds':g.BENCH_GROUND_BUILDS,'terrain_queries':g.BENCH_QUERIES}
                return row
            finally:
                try:
                    shutdown=lua.globals().shutdown
                    if shutdown: shutdown()
                except Exception:
                    pass


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--baseline-ref',default='v1.9.7')
    ap.add_argument('--baseline-dir',type=Path,
                    help='compare with a source snapshot containing src/eagle_direction_probe.lua, '
                         'src/stratagem_profiles.lua and src/solid_renderer.lua')
    ap.add_argument('--frames',type=int,default=280)
    ap.add_argument('--repeats',type=int,default=5)
    ap.add_argument('--solid-fill',action='store_true',help='exercise the real retained renderer with mock native APIs')
    ap.add_argument('--types',action='store_true',help='exercise type matching with mock native snapshots')
    ap.add_argument('--type-id',type=int,default=18)
    args=ap.parse_args()
    if args.baseline_dir:
        baseline_dir=args.baseline_dir.resolve()
        baseline_path=baseline_dir/'src/eagle_direction_probe.lua'
        profiles_path=baseline_dir/'src/stratagem_profiles.lua'
        renderer_path=baseline_dir/'src/solid_renderer.lua'
        baseline=baseline_path.read_bytes()
        baseline_profiles=profiles_path.read_bytes()
        baseline_renderer=renderer_path.read_bytes()
        baseline_name='snapshot:'+str(baseline_dir)
    else:
        baseline=subprocess.run(['git','show',args.baseline_ref+':src/eagle_direction_probe.lua'],
                                cwd=ROOT,capture_output=True,check=True).stdout
        baseline_profiles=subprocess.run(['git','show',args.baseline_ref+':src/stratagem_profiles.lua'],
                                         cwd=ROOT,capture_output=True,check=True).stdout
        baseline_renderer=None
        baseline_name=args.baseline_ref
    with tempfile.TemporaryDirectory() as tmp:
        old_dir=Path(tmp)/'baseline'/'src'
        old_dir.mkdir(parents=True,exist_ok=True)
        old=old_dir/'eagle_direction_probe.lua';old.write_bytes(baseline)
        old_profiles=old_dir/'stratagem_profiles.lua';old_profiles.write_bytes(baseline_profiles)
        old_renderer=old_dir/'solid_renderer.lua'
        if args.solid_fill:
            old_renderer.write_bytes(baseline_renderer if baseline_renderer is not None else
                subprocess.check_output(['git','show',args.baseline_ref+':src/solid_renderer.lua'],cwd=ROOT))
        # The rc14 snapshot also needs its packaged pure addon resources beside the entry
        # script (font, pose resolver, clock, and terrain modules). Keeping them in this
        # directory makes the benchmark load the actual packaged versions, not the current
        # working tree by accident.
        if args.baseline_dir:
            for source in baseline_dir.joinpath('src').glob('*.lua'):
                destination=old_dir/source.name
                if not destination.exists(): destination.write_bytes(source.read_bytes())
        result={'note':'Offline Lua CPU/allocation only, not game FPS. Uses synthetic confirmed guides, mock native renderer/terrain and type snapshots; does not measure live local-player pose or real engine/GPU work.',
                'baseline':baseline_name,'frames':args.frames,'repeats':args.repeats,'scenes':{}}
        for through in (False,True):
            for n in (1,4,8):
                rows={'baseline':[],'current':[]}
                # Alternate runs so warmup/thermal scheduling affects both versions similarly.
                for _ in range(args.repeats):
                    for key,path in (('baseline',old),('current',ROOT/'src/eagle_direction_probe.lua')):
                        rows[key].append(measure(path,n,args.frames,args.solid_fill,args.types,args.type_id,
                                                 old_renderer if key=='baseline' and args.solid_fill else None,
                                                 old_profiles if key=='baseline' else None,through,
                                                 expect_solid=(key=='current' or not through)))
                scene=f'{n}:through={str(through).lower()}'
                result['scenes'][scene]={key:{metric:round(statistics.median(r[metric] for r in runs),4)
                                    for metric in runs[0]} for key,runs in rows.items()}
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
