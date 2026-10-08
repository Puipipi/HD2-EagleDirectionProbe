"""Read-only audit against installed binaries and the working BTO query contract.

No game process is opened. No discovered function is executed. Regeneration is an
explicit developer action; a new game build must match the reference signatures.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from lupa.luajit21 import LuaRuntime

REPO = Path(__file__).resolve().parents[2]
GAME = Path(r'D:\Program Files (x86)\Steam\steamapps\common\Helldivers 2')
REFERENCE = Path(r'C:\Users\23825\AppData\Local\hd2arsenal\mods\HUD Ballistic Trajectory Overlay 15842 8 2026-10-06T02-55Z p61RCZ9H1_AR707895\Overlay\9ba626afa44a3aa3.patch_0')
SNAPSHOT = REPO.parents[1]/'mods/melee-vehicle-rescue/research/private'


class PE:
    def __init__(self, path):
        self.data = path.read_bytes()
        at = struct.unpack_from('<I', self.data, 0x3c)[0]
        assert self.data[:2] == b'MZ' and self.data[at:at+4] == b'PE\0\0'
        self.stamp = struct.unpack_from('<I', self.data, at+8)[0]
        self.size = struct.unpack_from('<I', self.data, at+0x50)[0]
        n = struct.unpack_from('<H', self.data, at+6)[0]
        optional = struct.unpack_from('<H', self.data, at+20)[0]
        self.sections = [struct.unpack_from('<8sIIIIIIHHI', self.data, at+24+optional+40*i)
                         for i in range(n)]

    def read(self, rva, length):
        for _, _, start, size, offset, *_ in self.sections:
            if start <= rva and rva+length <= start+size:
                return self.data[offset+rva-start:offset+rva-start+length]
        raise ValueError('unmapped RVA %x' % rva)


def derive():
    blob = REFERENCE.read_bytes()
    text = next(m.group().decode('utf-8') for m in
                re.finditer(rb'[\x09\x0a\x0d\x20-\xff]{150,}', blob) if b'ray_query' in m.group())
    start = text.index('local recipes = {', text.index('local native_recipes'))
    end = text.index('\nreturn recipes, function', start)
    recipes = LuaRuntime(encoding=None).execute((text[start:end]+'\nreturn recipes').encode())
    modules = {'helldivers2.exe': PE(GAME/'bin/helldivers2.exe'),
               'game.dll': PE(GAME/'data/game/game.dll')}
    # On-disk code is packed. Use the already captured, read-only decoded code
    # snapshot of the exact same build; never interpret packed bytes as code.
    snapshot = json.loads((SNAPSHOT/'snapshot.json').read_text(encoding='utf-8'))
    code_sections = {}
    for name, pe in modules.items():
        info = snapshot['modules'][name]
        assert (info['timestamp'], info['size']) == (pe.stamp, pe.size), 'snapshot build mismatch'
        code_sections[name] = []
        for section in info['sections']:
            if section['flags'] & 0x20000000:
                data = (SNAPSHOT/section['file']).read_bytes()
                assert hashlib.sha256(data).hexdigest() == section['sha256']
                code_sections[name].append((section['rva'], data))
    needed = {'ray_query', 'ray_inner_query', 'ray_hit44_writer', 'ray_world_lookup',
              'collision_0', 'collision_1', 'query_owner'}
    rows, fields = [], {}
    for _, recipe in recipes.items():
        name, module = recipe[b'name'].decode(), recipe[b'module'].decode()
        if name not in needed:
            continue
        pe = modules[module]
        rva = next(h[3] for _, h in recipe[b'hints'].items()
                   if h[1] == pe.stamp and h[2] == pe.size)
        code = next(data[rva-at:rva-at+recipe[b'size']] for at, data in code_sections[module]
                    if at <= rva and rva+recipe[b'size'] <= at+len(data))
        for _, piece in recipe[b'pieces'].items():
            assert code[piece[1]:piece[1]+len(piece[2])] == piece[2], name
        fields[name] = {f[1].decode(): rva+f[3]+struct.unpack_from('<i', code, f[2])[0]
                        for _, f in recipe[b'fields'].items()}
        import zlib
        djb = 5381
        for byte in code:
            djb = (djb*33+byte) % 4294967296
        rows.append({'name': name, 'module': module, 'rva': rva, 'size': len(code),
                     'adler32': zlib.adler32(code), 'djb32': djb})
        print('%s: %d verified bytes at 0x%x' % (name, len(code), rva))
    addresses = {r['name']: r['rva'] for r in rows}
    assert fields['ray_query']['c8d'] == addresses['ray_inner_query']
    assert fields['ray_inner_query']['c3f9'] == addresses['ray_hit44_writer']
    api = fields['collision_0']['r6']
    assert all(v == api for v in fields['collision_0'].values())
    assert fields['collision_1']['r0'] == api
    return {'reference_sha256': hashlib.sha256(blob).hexdigest(),
            'modules': {k: {'stamp': v.stamp, 'size': v.size,
                           'sha256': hashlib.sha256(v.data).hexdigest()} for k, v in modules.items()},
            'code': rows,
            'layout': {'owner': fields['query_owner']['r1b'], 'api': api,
                       'presets': fields['ray_query']['r28'], 'worlds': fields['ray_world_lookup']['r2'],
                       'query': addresses['ray_query']}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    derived = derive()
    target = REPO/'src/terrain_contract.json'
    if args.generate:
        target.write_text(json.dumps(derived, indent=2)+'\n', encoding='utf-8')
        def lua_literal(value):
            if isinstance(value, dict):
                return '{'+','.join('['+json.dumps(k)+']='+lua_literal(v) for k, v in value.items())+'}'
            if isinstance(value, list):
                return '{'+','.join(lua_literal(v) for v in value)+'}'
            return json.dumps(value)
        (REPO/'src/terrain_contract.lua').write_text(
            '-- HD2-Addon: mods/codex/eagle_terrain_contract\n'
            '-- Generated by audit_terrain_contract.py; derived fingerprints, no game code.\n'
            'return '+lua_literal(derived)+'\n', encoding='utf-8')
    else:
        assert json.loads(target.read_text(encoding='utf-8')) == derived, 'contract changed'
    print('Current binary / reference contract audit OK; no native calls executed')
