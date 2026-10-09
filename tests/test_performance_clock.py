"""The optional QPC clock must measure sub-frame intervals and degrade honestly."""
import unittest
from pathlib import Path

from lupa.luajit21 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class PerformanceClockTest(unittest.TestCase):
    def run_lua(self, script):
        path = ROOT / "src/performance_clock.lua"
        self.assertTrue(path.exists(), "performance clock module is missing")
        lua = LuaRuntime()
        lua.globals().clock_path = str(path)
        lua.execute("local P=assert(loadfile(clock_path))()\n" + script)

    def test_qpc_uses_frequency_once_reuses_buffer_and_preserves_submillisecond_delta(self):
        self.run_lua(r'''
local realffi=require('ffi')
local count=realffi.new('int64_t',9007199254740992)
local qpf_calls,qpc_calls=0,0
local qpc_buffers={}
local kernel={
    QueryPerformanceFrequency=function(buf)
        qpf_calls=qpf_calls+1;buf[0]=10000000;return 1
    end,
    QueryPerformanceCounter=function(buf)
        qpc_calls=qpc_calls+1;qpc_buffers[#qpc_buffers+1]=buf
        buf[0]=count;count=count+realffi.new('int64_t',1000);return 1
    end,
}
local mockffi={os='Windows',abi=function() return true end,cdef=function() end,
    new=realffi.new,load=function(name) assert(name=='kernel32');return kernel end}
local P=assert(loadfile(clock_path))()
local clock=P.new({ffi=mockffi})
local t0,t1,t2=clock.now_ms(),clock.now_ms(),clock.now_ms()
assert(clock.source=='qpc' and clock.precise==true)
assert(math.abs(clock.resolution_ms-0.0001)<1e-12)
assert(qpf_calls==1,'frequency must be queried once')
assert(qpc_calls==3,'one origin read plus one counter read per now_ms call')
assert(qpc_buffers[1]==qpc_buffers[2] and qpc_buffers[2]==qpc_buffers[3],
    'counter buffer must be reused')
assert(t0==0 and math.abs((t1-t0)-0.1)<1e-9 and math.abs((t2-t1)-0.1)<1e-9,
    'relative-origin subtraction lost a sub-ms delta at a large counter origin')
''')

    def test_non_windows_platform_uses_explicit_inexact_fallback_without_loading_dll(self):
        self.run_lua(r'''
local calls=0;local t=20
local mockffi={os='Linux',abi=function() return true end,
    load=function() calls=calls+1;error('must not load Windows DLL') end}
local P=assert(loadfile(clock_path))()
local clock=P.new({ffi=mockffi,fallback_now=function() t=t+0.02;return t end,
    fallback_source='fallback-fixture',fallback_resolution_ms=15.6})
local a,b=clock.now_ms(),clock.now_ms()
assert(clock.source=='fallback-fixture' and clock.precise==false)
assert(clock.resolution_ms==15.6 and b>=a and calls==0)
''')

    def test_frequency_failure_falls_back_and_never_claims_precision(self):
        self.run_lua(r'''
local realffi=require('ffi');local t=50;local qpc=0
local kernel={
    QueryPerformanceFrequency=function(buf) buf[0]=0;return 0 end,
    QueryPerformanceCounter=function() qpc=qpc+1;return 0 end,
}
local mockffi={os='Windows',abi=function() return true end,cdef=function() end,
    new=realffi.new,load=function() return kernel end}
local P=assert(loadfile(clock_path))()
local clock=P.new({ffi=mockffi,fallback_now=function() t=t+0.25;return t end,
    fallback_source='fallback-test',fallback_resolution_ms=1})
local a,b=clock.now_ms(),clock.now_ms()
assert(clock.source=='fallback-test' and clock.precise==false and clock.resolution_ms==1)
assert(b>a and qpc==0,'failed QPF must not attempt QPC calls')
''')

    def test_runtime_qpc_failure_bridges_to_monotonic_fallback(self):
        self.run_lua(r'''
local realffi=require('ffi');local count=realffi.new('int64_t',1000000)
local fail=false;local fallback=100
local kernel={
    QueryPerformanceFrequency=function(buf) buf[0]=1000000;return 1 end,
    QueryPerformanceCounter=function(buf)
        if fail then error('counter unavailable') end
        buf[0]=count;count=count+realffi.new('int64_t',100);return 1
    end,
}
local mockffi={os='Windows',abi=function() return true end,cdef=function() end,
    new=realffi.new,load=function() return kernel end}
local P=assert(loadfile(clock_path))()
local clock=P.new({ffi=mockffi,fallback_now=function() return fallback end,
    fallback_source='fallback-test',fallback_resolution_ms=15.6})
local a,b=clock.now_ms(),clock.now_ms()
assert(clock.source=='qpc' and b>a)
fail=true;local c=clock.now_ms()
fallback=fallback+0.25;local d=clock.now_ms()
assert(clock.source=='fallback-qpc-error' and clock.precise==false,
    'runtime fallback must expose its inexact source: '..tostring(clock.source))
assert(c>=b and d>=c and math.abs(d-c-0.25)<1e-8,
    'fallback after QPC error must bridge from the last QPC time without going backward: '
    ..tostring(b)..','..tostring(c)..','..tostring(d)..','..tostring(fallback)..','..tostring(clock.source))
''')

    def test_ffi_or_kernel_load_failure_is_caught_and_uses_fallback(self):
        self.run_lua(r'''
local P=assert(loadfile(clock_path))()
for _,opts in ipairs({
    {ffi=false},
    {ffi={os='Windows',abi=function() return true end,cdef=function() end,
        new=require('ffi').new,load=function() error('kernel32 unavailable') end}},
}) do
    local n=4
    opts.fallback_now=function() n=n+1;return n end
    opts.fallback_source='fallback-unavailable'
    opts.fallback_resolution_ms=15.6
    local clock=P.new(opts)
    local a,b=clock.now_ms(),clock.now_ms()
    assert(clock.source=='fallback-unavailable' and clock.precise==false)
    assert(b>=a,'load failure made the fallback clock non-monotonic')
end
''')

    def test_module_import_and_clock_construction_do_not_load_ffi(self):
        self.run_lua(r'''
        local real_require=require
        require=function(name)
            if name=='ffi' then error('FFI must remain lazy until first read') end
            return real_require(name)
        end
local P=assert(loadfile(clock_path))()
local clock=P.new({fallback_now=function() return 1 end})
assert(clock.source=='fallback-not-initialized' and clock.precise==false)
assert(clock.now_ms()==0,'first use should safely select the fallback clock')
assert(clock.source=='fallback-os.clock' and clock.precise==false)
require=real_require
''')


if __name__ == "__main__":
    unittest.main()
