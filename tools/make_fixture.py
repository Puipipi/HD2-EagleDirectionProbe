"""Generate synthetic probe JSONL with a KNOWN answer, to self-test the analyzer.

Two kinds of fixture, because two different mistakes are possible:

* `strafing` and `cluster` check that the per-stratagem rules are found at all. They
  differ only in the aircraft's ground track, and the analyzer must name a different
  rule for each - a tool that reports the same rule for both has no discriminating
  power and its readings mean nothing.
* `deflected` checks that a deflected call is not read as the rule being wrong. One
  clean call plus one turned 55 degrees is what the reported obstacle avoidance looks
  like, and it must come back as a deflection, not as "no rule fits".

Known answers, given the player at the origin and the beacon landing due east (so the
player-to-beacon bearing is 0 degrees):

  strafing  aircraft travels +x  -> measured ~0   -> along_from_behind
  cluster   aircraft travels +y  -> measured ~90  -> perp_left
  deflected call 2 is rotated 55 degrees off the strafing track

Usage:
  python make_fixture.py --scenario strafing --out strafing.jsonl
"""
import argparse
import json
import math

UP_Z = 60.0
BEACON_HEX = '16f397ca5f51f271'

# Which munition identities each scenario pretends appeared, so the analyzer can name
# the stratagem the way it will have to on a real log.
SCENARIO_SRC = {
    'strafing': ['eagle_gunpods', 'eagle_base'],
    'cluster': ['eagle_cluster'],
    'deflected': ['eagle_gunpods', 'eagle_base'],
}


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


def rotate_about(start, end, degrees):
    """Rotate a ground track about its midpoint, standing in for a deflection."""
    cx, cy = (start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0
    rad = math.radians(degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    rows = []
    samples = 30
    for i in range(samples):
        u = i / (samples - 1)
        x = start[0] + (end[0] - start[0]) * u - cx
        y = start[1] + (end[1] - start[1]) * u - cy
        rows.append((u * 4.0, [round(x * cos_a - y * sin_a + cx, 4),
                               round(x * sin_a + y * cos_a + cy, 4),
                               round(start[2] + (end[2] - start[2]) * u + 0.5 * u, 4)]))
    return rows


def emit_call(lines, call_id, track, srcs, t_offset=0.0):
    beacons = beacon_arc([0.0, 0.0, 1.5], [40.0, 0.0, 0.0])
    lines.append({'kind': 'call_begin', 't': t_offset, 'call': call_id})
    for src in srcs:
        lines.append({'kind': 'call_stratagem', 't': t_offset, 'call': call_id,
                      'note': '%s=?' % src})
    for i in range(max(len(beacons), len(track))):
        rec = {'kind': 'sample', 't': t_offset, 'call': call_id, 'n': i + 1}
        if i < len(beacons):
            bt, bp = beacons[i]
            rec['beacons'] = [{'src': 'beacon', 'id': BEACON_HEX, 'p': bp}]
            rec['t'] = max(rec['t'], t_offset + bt)
        if i < len(track):
            et, ep = track[i]
            # One entry per declared identity, all at the same point: this is what the
            # real probe produces when a stratagem has more than one munition unit.
            rec['eagles'] = [{'src': src, 'id': 'eagle', 'p': ep, 'pose': True}
                             for src in srcs]
            rec['t'] = max(rec['t'], t_offset + et)
        lines.append(rec)
    lines.append({'kind': 'call_end', 't': t_offset + 4.0, 'call': call_id,
                  'note': 'timeout'})


def emit(path, scenario):
    lines = [{'kind': 'capabilities', 't': 0,
              'note': 'Application=table, World=table, Unit=table, Vector3=table'}]
    srcs = SCENARIO_SRC[scenario]

    # Strafing run: along the player-to-beacon line, coming from behind the player.
    # Two calls of the SAME stratagem, both travelling the same way - the second is
    # only shifted, because a repeated call must not look like a different rule.
    strafing = [([-300.0, -2.0, UP_Z], [300.0, 2.0, UP_Z + 0.5]),
                ([-295.0, -305.0, UP_Z], [305.0, -295.0, UP_Z + 0.5])]
    # Cluster bomb: perpendicular to that line, likewise both calls the same way.
    cluster = [([38.0, -300.0, UP_Z], [42.0, 300.0, UP_Z + 0.5]),
               ([-40.0, -295.0, UP_Z], [-44.0, 305.0, UP_Z + 0.5])]

    if scenario == 'strafing':
        for n, (a, b) in enumerate(strafing, start=1):
            emit_call(lines, n, eagle_track(a, b), srcs, t_offset=(n - 1) * 10.0)
    elif scenario == 'cluster':
        for n, (a, b) in enumerate(cluster, start=1):
            emit_call(lines, n, eagle_track(a, b), srcs, t_offset=(n - 1) * 10.0)
    else:
        a, b = strafing[0]
        emit_call(lines, 1, eagle_track(a, b), srcs)
        emit_call(lines, 2, rotate_about(a, b, 55.0), srcs, t_offset=10.0)

    with open(path, 'w', encoding='utf-8') as fh:
        for rec in lines:
            fh.write(json.dumps(rec) + '\n')
    print('wrote %s (%s), %d records' % (path, scenario, len(lines)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenario', required=True,
                    choices=('strafing', 'cluster', 'deflected'))
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    emit(args.out, args.scenario)
