"""Read-only fingerprint/world audit. Does not call game functions or attach a debugger."""
import argparse
import ctypes as c
import json
import struct
import zlib
from ctypes import wintypes as w
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--pid',required=True,type=int)
args=parser.parse_args()
contract=json.loads((Path(__file__).resolve().parents[2]/'src/terrain_contract.json').read_text())
k=c.WinDLL('kernel32',use_last_error=True)
class Entry(c.Structure):
    _fields_=[('size',w.DWORD),('mid',w.DWORD),('pid',w.DWORD),('g',w.DWORD),('p',w.DWORD),
              ('base',c.c_void_p),('length',w.DWORD),('handle',w.HMODULE),
              ('name',w.WCHAR*256),('path',w.WCHAR*260)]
k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
k.Module32FirstW.argtypes=[w.HANDLE,c.POINTER(Entry)];k.Module32FirstW.restype=w.BOOL
k.Module32NextW.argtypes=[w.HANDLE,c.POINTER(Entry)];k.Module32NextW.restype=w.BOOL
k.CloseHandle.argtypes=[w.HANDLE]
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
k.ReadProcessMemory.restype=w.BOOL
snap=k.CreateToolhelp32Snapshot(0x18,args.pid)
assert snap and snap!=c.c_void_p(-1).value,'module enumeration unavailable'
entry=Entry();entry.size=c.sizeof(entry);bases={}
try:
    ok=k.Module32FirstW(snap,c.byref(entry))
    while ok:
        if entry.name.lower() in contract['modules']:bases[entry.name.lower()]=entry.base
        ok=k.Module32NextW(snap,c.byref(entry))
finally:k.CloseHandle(snap)
assert len(bases)==2,'game modules unavailable'
handle=k.OpenProcess(0x1010,False,args.pid)
assert handle,'read-only process access unavailable'
def read(at,n):
    b=c.create_string_buffer(n);done=c.c_size_t()
    assert k.ReadProcessMemory(handle,at,b,n,c.byref(done)) and done.value==n,'short read'
    return b.raw
def ptr(at):return struct.unpack('<Q',read(at,8))[0]
try:
    for r in contract['code']:
        data=read(bases[r['module']]+r['rva'],r['size']);h=5381
        for v in data:h=(h*33+v)%4294967296
        assert zlib.adler32(data)==r['adler32'] and h==r['djb32'],r['name']
        print(r['name'],'live code fingerprint OK')
    l=contract['layout'];exe=bases['helldivers2.exe'];game=bases['game.dll']
    owner=ptr(game+l['owner']);qs=ptr(owner+8);world=ptr(qs)
    qh=struct.unpack('<I',read(qs+0xa0,4))[0]
    assert 0x80000000<=qh<0x80000100,'query handle unavailable'
    preset=struct.unpack('<5I',read(exe+l['presets']+(qh-0x80000000)*20,20))
    assert preset[0]<4 and preset[1:]==(2,5,0x3e24ec53,0x80000009),preset
    assert ptr(exe+l['worlds']+preset[0]*8)==world
    assert ptr(ptr(game+l['api'])+0x68)==exe+l['query']
    print('Live query world / preset / wrapper address OK; no game calls or writes executed.')
finally:k.CloseHandle(handle)
