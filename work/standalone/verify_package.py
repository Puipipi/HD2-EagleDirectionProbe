"""Verify the delivered ZIP against source and the previously shipped native modules."""
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

import build_probe as build

sys.path.insert(0, str(build.VENDOR))
from archive import ARCHIVE, TYPE, resource_hash


def resources(path):
    with zipfile.ZipFile(path) as package:
        assert package.testzip() is None, 'ZIP CRC failure'
        manifest = json.loads(package.read('manifest.json'))
        assert manifest['Guid'] == build.GUID and manifest['Version'] == 1
        blob = package.read('Addon/' + ARCHIVE)
    magic, version, count = struct.unpack_from('<III', blob)
    assert magic == 0xF0000011 and version == 1 and count == 3
    result = {}
    for i in range(count):
        fields = struct.unpack_from('<7Q6I', blob, 104 + i * 80)
        name, kind, offset, length = fields[0], fields[1], fields[2], fields[7]
        assert kind == TYPE and offset + length <= len(blob)
        size, encoding = struct.unpack_from('<II', blob, offset)
        assert size + 8 == length and encoding == 2
        result[name] = blob[offset + 8:offset + length]
    return result


def main():
    path = build.DIST / ('HD2-EagleDirectionProbe-%s.zip' % build.VERSION)
    current = resources(path)
    with zipfile.ZipFile(path) as package:
        manifest=json.loads(package.read('manifest.json'))
        assert manifest['IconPath']=='cover.png', 'missing manager cover reference'
        assert all(option['Image']=='cover.png' and option['Include']==['Addon']
                   for option in manifest['Options']), 'option cover or deploy scope mismatch'
        cover=package.read(manifest['IconPath'])
        assert cover==build.COVER.read_bytes(), 'packaged cover differs from asset'
        assert cover.startswith(b'\x89PNG\r\n\x1a\n'), 'cover is not a PNG'
        width,height=struct.unpack_from('>II',cover,16)
        assert width==height and width>=512, 'cover should be a readable square image'
    for name, source in {build.RESOURCE: build.SOURCE, **build.EXTRA_SOURCES}.items():
        assert current[resource_hash(name)] == source.read_bytes(), name + ' differs from source'
    previous = resources(build.DIST / 'HD2-EagleDirectionProbe-1.9.9.zip')
    for name in build.EXTRA_SOURCES:
        assert current[resource_hash(name)] == previous[resource_hash(name)], 'native module changed'
    print('ZIP CRC, manifest, all 3 resource payloads: OK')
    print('Native terrain resources byte-identical to 1.9.9: OK')
    print('Manager IconPath/option Image and bundled square PNG: OK (%d x %d)' % (width,height))
    print('Bytes:', path.stat().st_size)
    print('SHA256:', hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
