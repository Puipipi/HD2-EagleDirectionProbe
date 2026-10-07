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


def rotated_track(start, end, degrees, up_index=2):
    """An eagle track rotated about the beacon, to stand in for an obstacle deflection."""
    cx, cy = (start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0
    rad = math.radians(degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    rows = []
    samples = 30
    for i in range(samples):
        u = i / (samples - 1)
        x = start[0] + (end[0] - start[0]) * u - cx
        y = start[1] + (end[1] - start[1]) * u - cy
        rx = x * cos_a - y * sin_a + cx
        ry = x * sin_a + y * cos_a + cy
        rz = (start[2] + (end[2] - start[2]) * u) + 0.5 * u
        rows.append((u * 4.0, [round(rx, 4), round(ry, 4), round(rz, 4)]))
    return rows


def emit_call(lines, call_id, eagles, t_offset=0.0):
    """Emit one call's samples; every eagle track in the list is written per sample."""
    beacons = beacon_arc([0.0, 0.0, 1.5], [40.0, 0.0, 0.0])
    lines.append({'kind': 'call_begin', 't': t_offset, 'call': call_id})
    length = max([len(beacons)] + [len(e) for e in eagles])
    for i in range(length):
        rec = {'kind': 'sample', 't': t_offset, 'call': call_id, 'n': i + 1}
        if i < len(beacons):
            bt, bp = beacons[i]
            rec['beacons'] = [{'id': '16f397ca5f51f271', 'p': bp}]
            rec['t'] = max(rec['t'], t_offset + bt)
        for track in eagles:
            if i < len(track):
                et, ep = track[i]
                rec['eagles'] = rec.get('eagles', []) + [
                    {'id': '2ea01cb1676aca29', 'p': ep, 'pose': True}]
                rec['t'] = max(rec['t'], t_offset + et)
        lines.append(rec)
    lines.append({'kind': 'call_end', 't': t_offset + 4.0, 'call': call_id,
                  'note': 'timeout'})


def emit(path, scenario):
    lines = [{'kind': 'capabilities', 't': 0,
              'note': 'Application=table, World=table, Unit=table, Vector3=table'}]

    if scenario == 'h1':
        # Perpendicular to the player->beacon line: north/south, 600 m long.
        emit_call(lines, 1, [eagle_track([38.0, -300.0, UP_Z], [42.0, 300.0, UP_Z + 0.5])])
    elif scenario == 'h2':
        # Along that line: east/west.
        emit_call(lines, 1, [eagle_track([-300.0, -2.0, UP_Z], [300.0, 2.0, UP_Z + 0.5])])
    else:
        # What obstacle avoidance should look like: one clean call on the
        # perpendicular, then one deflected well off it (and a third, clean again,
        # so the reader can see the deflection is the exception rather than the rule).
        clean = [[38.0, -300.0, UP_Z], [42.0, 300.0, UP_Z + 0.5]]
        emit_call(lines, 1, [eagle_track(clean[0], clean[1])])
        emit_call(lines, 2, [rotated_track(clean[0], clean[1], 55.0)], t_offset=10.0)
        emit_call(lines, 3, [eagle_track(clean[0], clean[1])], t_offset=20.0)

    with open(path, 'w', encoding='utf-8') as fh:
        for rec in lines:
            fh.write(json.dumps(rec) + '\n')
    print('wrote %s (%s), %d records' % (path, scenario, len(lines)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', required=True, choices=('h1', 'h2', 'mixed'))
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    emit(args.out, args.scenario)
