"""Generate a synthetic probe JSONL with a KNOWN answer, to self-test the analyzer.

THROWAWAY SPIKE TOOL.

Two fixtures:
  h1 -- the Eagle's run axis is perpendicular to the player->beacon line
        (the community claim). The analyzer must report MATCH.
  h2 -- the Eagle's run axis is along the player->beacon line
        (i.e. NOT perpendicular). The analyzer must report no match.

A tool that cannot separate a case it should accept from one it should reject is not
evidence, so this runs before the analyzer is trusted on real logs.

Usage:
  python make_fixture.py --scenario h1 --out h1.jsonl
"""
import argparse
import json
import math

UP_Z = 60.0


def beacon_arc(origin, landing, samples=25, peak=6.0):
    """A simple parabola from the hand to the landing point."""
    rows = []
    for i in range(samples):
        u = i / (samples - 1)
        x = origin[0] + (landing[0] - origin[0]) * u
        y = origin[1] + (landing[1] - origin[1]) * u
        z = origin[2] + (landing[2] - origin[2]) * u + peak * 4 * u * (1 - u)
        rows.append((u * 3.0, [round(x, 4), round(y, 4), round(z, 4)]))
    return rows


def eagle_track(start, end, samples=30):
    rows = []
    for i in range(samples):
        u = i / (samples - 1)
        x = start[0] + (end[0] - start[0]) * u
        y = start[1] + (end[1] - start[1]) * u
        z = start[2] + (end[2] - start[2]) * u
        rows.append((u * 4.0, [round(x, 4), round(y, 4), round(z, 4)]))
    return rows


def emit(path, scenario):
    # Player at the origin; the beacon is thrown due east and lands 40 m away.
    throw_origin = [0.0, 0.0, 1.5]
    landing = [40.0, 0.0, 0.0]
    beacons = beacon_arc(throw_origin, landing)

    # H1: run axis perpendicular to the player->beacon line -> north/south, 600 m long.
    # H2: run axis along that line -> east/west.
    if scenario == 'h1':
        eagle = eagle_track([38.0, -300.0, UP_Z], [42.0, 300.0, UP_Z + 0.5])
    else:
        eagle = eagle_track([-300.0, -2.0, UP_Z], [300.0, 2.0, UP_Z + 0.5])

    lines = [{'kind': 'capabilities', 't': 0,
              'note': 'Application=table, World=table, Unit=table, Vector3=table'}]
    lines.append({'kind': 'call_begin', 't': 0.0, 'call': 1})

    for i in range(max(len(beacons), len(eagle))):
        t = beacons[min(i, len(beacons) - 1)][0]
        rec = {'kind': 'sample', 't': t, 'call': 1, 'n': i + 1}
        if i < len(beacons):
            bt, bp = beacons[i]
            rec['beacons'] = [{'id': '16f397ca5f51f271', 'p': bp}]
        if i < len(eagle):
            et, ep = eagle[i]
            rec['eagles'] = [{'id': '2ea01cb1676aca29', 'p': ep, 'pose': True}]
            rec['t'] = max(rec['t'], et)
        lines.append(rec)

    lines.append({'kind': 'call_end', 't': 4.0, 'call': 1, 'note': 'timeout'})

    with open(path, 'w', encoding='utf-8') as fh:
        for rec in lines:
            fh.write(json.dumps(rec) + '\n')
    print('wrote %s (%s), %d records' % (path, scenario, len(lines)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', required=True, choices=('h1', 'h2'))
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    emit(args.out, args.scenario)
