"""Offline analyzer for the Eagle direction probe's JSONL.

THROWAWAY SPIKE TOOL. Reads the probe log and answers one question: is the Eagle's
incoming direction predictable from things already readable at call time, or does it
depend on the aircraft's own live state?

It fits two hypotheses against the measured geometry:

  H1  the run axis is perpendicular to the player->beacon line
      (the community claim; if true, an arrow can be drawn at throw time)
  H2  the run axis is the aircraft's own heading, unrelated to that line
      (if true, a prediction mod must read the aircraft, and its lead time is
       whatever the gap is between first sighting and impact)

Nothing here is a verdict on its own: it prints the residuals for both, per call and
pooled, so the numbers decide.

Usage:
  python analyze_eagle_probe.py <probe.jsonl> [--json out.json] [--up auto|z|y]
"""
import argparse
import json
import math
import sys

# The engine's own vertical axis is not assumed: the aircraft flies roughly level, so
# the axis with the smallest spread across its track is the vertical one. Auto-detect
# and report the choice, and allow an override.
UP_CANDIDATES = ('z', 'y', 'x')
AXIS_INDEX = {'x': 0, 'y': 1, 'z': 2}


def bearing(dx, dy):
    """Degrees, atan2 convention, in the horizontal plane."""
    return math.degrees(math.atan2(dy, dx))


def norm180(deg):
    while deg <= -180.0:
        deg += 360.0
    while deg > 180.0:
        deg -= 360.0
    return deg


def horizontal(point, up):
    idx = AXIS_INDEX[up]
    others = [i for i in range(3) if i != idx]
    return point[others[0]], point[others[1]]


def load(path):
    records = []
    with open(path, encoding='utf-8') as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                print('line %d is not JSON (%s); skipping' % (lineno, exc))
    return records


def choose_up(records, forced):
    if forced != 'auto':
        return forced, 'forced on the command line'
    spread = {}
    for axis in UP_CANDIDATES:
        idx = AXIS_INDEX[axis]
        values = []
        for rec in records:
            for unit in rec.get('eagles') or []:
                if 'p' in unit:
                    values.append(unit['p'][idx])
        spread[axis] = (max(values) - min(values)) if values else 0.0
    best = min(spread, key=lambda a: spread[a])
    return best, 'auto-detected (axis ranges: %s)' % ', '.join(
        '%s=%.1fm' % (a, spread[a]) for a in UP_CANDIDATES)


def tracks(records, key, up):
    """Per-unit track of (t, point) from sample and idle records."""
    out = {}
    for rec in records:
        if rec.get('kind') not in ('sample', 'idle_eagle'):
            continue
        for unit in rec.get(key) or []:
            if 'p' not in unit:
                continue
            out.setdefault(unit['id'], []).append((rec.get('t', 0.0), unit['p'], unit.get('f')))
    for rows in out.values():
        rows.sort(key=lambda r: r[0])
    return out


def track_direction(rows, up):
    """Mean horizontal direction of travel, weighted by distance moved."""
    sx = sy = 0.0
    for (t0, p0, _), (t1, p1, _) in zip(rows, rows[1:]):
        if t1 - t0 <= 0:
            continue
        x0, y0 = horizontal(p0, up)
        x1, y1 = horizontal(p1, up)
        sx += x1 - x0
        sy += y1 - y0
    if sx == 0.0 and sy == 0.0:
        return None, 0.0
    return bearing(sx, sy), math.hypot(sx, sy)


def forward_direction(rows, up):
    """Mean of the aircraft's own forward vectors, if the probe captured them."""
    sx = sy = 0.0
    n = 0
    idx = AXIS_INDEX[up]
    others = [i for i in range(3) if i != idx]
    for _, _, f in rows:
        if not f:
            continue
        sx += f[others[0]]
        sy += f[others[1]]
        n += 1
    if n == 0 or (sx == 0.0 and sy == 0.0):
        return None
    return bearing(sx, sy)


def analyze_call(call_id, records, up):
    beacons = tracks(records, 'beacons', up)
    eagles = tracks(records, 'eagles', up)

    beacon_rows = None
    for _, rows in beacons.items():
        if beacon_rows is None or len(rows) > len(beacon_rows):
            beacon_rows = rows
    if not beacon_rows or len(beacon_rows) < 2:
        return {'call': call_id, 'status': 'no usable beacon track'}

    origin = beacon_rows[0]
    settled = beacon_rows[-1]
    throw_bearing, throw_len = track_direction(beacon_rows, up)
    line_bearing = bearing(
        horizontal(settled[1], up)[0] - horizontal(origin[1], up)[0],
        horizontal(settled[1], up)[1] - horizontal(origin[1], up)[1])

    eagle_rows = None
    for _, rows in eagles.items():
        if eagle_rows is None or len(rows) > len(eagle_rows):
            eagle_rows = rows

    out = {
        'call': call_id,
        'status': 'ok',
        'throw_origin': origin[1],
        'beacon_landing': settled[1],
        'throw_bearing_deg': throw_bearing,
        'player_to_beacon_bearing_deg': line_bearing,
        'h1_predicted_axis_deg': norm180(line_bearing + 90.0),
        'h1_predicted_axis_also_deg': norm180(line_bearing - 90.0),
        'samples': len(beacon_rows),
        'duration_s': round(beacon_rows[-1][0] - beacon_rows[0][0], 3),
    }
    if not eagle_rows or len(eagle_rows) < 2:
        out['eagle'] = 'not seen in this call'
        return out

    measured, travelled = track_direction(eagle_rows, up)
    out['eagle_samples'] = len(eagle_rows)
    out['eagle_first_seen_s'] = round(eagle_rows[0][0] - beacon_rows[0][0], 3)
    out['eagle_visible_for_s'] = round(eagle_rows[-1][0] - eagle_rows[0][0], 3)
    out['eagle_travel_m_horizontal'] = round(travelled, 2)
    out['eagle_forward_deg'] = forward_direction(eagle_rows, up)
    if measured is not None:
        out['measured_axis_deg'] = measured
        d_plus = norm180(measured - out['h1_predicted_axis_deg'])
        d_minus = norm180(measured - out['h1_predicted_axis_also_deg'])
        out['h1_error_plus_deg'] = round(d_plus, 2)
        out['h1_error_minus_deg'] = round(d_minus, 2)
        out['h1_error_best_deg'] = round(min(abs(d_plus), abs(d_minus)), 2)
        out['h1_error_signed_deg'] = round(
            d_plus if abs(d_plus) <= abs(d_minus) else d_minus, 2)
        out['h1_axis_matches'] = out['h1_error_best_deg'] <= 20.0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl')
    ap.add_argument('--json', default=None)
    ap.add_argument('--up', default='auto', choices=('auto', 'x', 'y', 'z'))
    args = ap.parse_args()

    records = load(args.jsonl)
    if not records:
        print('no records in %s' % args.jsonl)
        return 1

    up, up_why = choose_up(records, args.up)
    calls = sorted({r['call'] for r in records if r.get('kind') in ('sample', 'call_begin')
                    and r.get('call')})
    caps = [r for r in records if r.get('kind') == 'capabilities']
    stops = [r for r in records if r.get('kind') == 'stopped']

    print('records            : %d' % len(records))
    print('vertical axis      : %s  (%s)' % (up, up_why))
    if caps:
        print('stingray on load   : %s' % caps[0].get('note'))
    idle = [r for r in records if r.get('kind') == 'idle_eagle']
    print('idle eagle samples : %d  (aircraft visible between calls?)' % len(idle))
    if stops:
        print('probe note         : %s' % stops[0].get('note'))
    print('calls detected     : %d' % len(calls))

    results = []
    for call_id in calls:
        subset = [r for r in records if r.get('call') == call_id]
        results.append(analyze_call(call_id, subset, up))

    print()
    for row in results:
        print('--- call %s ---' % row['call'])
        if row.get('status') != 'ok':
            print('   %s' % row.get('status'))
            continue
        print('   player->beacon bearing : %.1f deg' % row['player_to_beacon_bearing_deg'])
        print('   H1 predicts axis       : %.1f deg (or %.1f)'
              % (row['h1_predicted_axis_deg'], row['h1_predicted_axis_also_deg']))
        if 'measured_axis_deg' not in row:
            print('   measured axis          : %s' % row.get('eagle'))
            continue
        print('   MEASURED eagle axis    : %.1f deg' % row['measured_axis_deg'])
        print('   H1 error               : %.1f deg (%s)'
              % (row['h1_error_best_deg'],
                 'MATCH' if row['h1_axis_matches'] else 'does not match'))
        print('   eagle first seen at    : +%.2fs after the throw' % row['eagle_first_seen_s'])
        print('   eagle visible for      : %.2fs, travelling %.1fm'
              % (row['eagle_visible_for_s'], row['eagle_travel_m_horizontal']))
        if row.get('eagle_forward_deg') is not None:
            print('   aircraft forward vector: %.1f deg' % row['eagle_forward_deg'])

    usable = [r for r in results if 'measured_axis_deg' in r]
    print()
    if not usable:
        print('VERDICT: no call produced both a beacon track and an Eagle track.')
        print('         Nothing is decided yet - re-run with more calls, or turn on')
        print('         FALLBACK_WORLD_SCAN if the Eagle was never listed.')
    else:
        matches = sum(1 for r in usable if r['h1_axis_matches'])
        errors = [r['h1_error_best_deg'] for r in usable]
        mean = sum(errors) / len(errors)
        spread = max(errors) - min(errors)
        print('VERDICT over %d measurable call(s):' % len(usable))
        print('  H1 matched in %d of %d' % (matches, len(usable)))
        print('  H1 error: mean %.1f deg, range %.1f..%.1f deg'
              % (mean, min(errors), max(errors)))
        if matches == len(usable) and spread < 25.0:
            print('  -> H1 consistent with the data. The axis looks computable at throw')
            print('     time from the player and the beacon, which is what a prediction')
            print('     mod needs. Confirm with a second mission before building.')
        else:
            print('  -> H1 is NOT cleanly supported. Look at the aircraft forward')
            print('     vector and at the idle_eagle samples: the axis may follow the')
            print('     aircraft\'s own live heading, which changes the design.')
        leads = [r['eagle_first_seen_s'] for r in usable]
        print('  Lead time (first sighting -> beacon settled): %.2f..%.2f s'
              % (min(leads), max(leads)))

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({'vertical_axis': up, 'axis_choice': up_why,
                       'calls': results}, fh, indent=1)
        print('\nwrote %s' % args.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
