"""Offline analyzer for the Eagle direction probe's JSONL.

Reads the probe log and answers one question: for each Eagle stratagem, is the
aircraft's incoming direction predictable from things already readable at call time?

Why this is per-stratagem and not one rule. The player reports that different Eagle
stratagems have different DEFAULT approach directions - the strafing run comes along
the player-to-beacon line from behind the player, the cluster bomb comes
perpendicular from the left - and that the aircraft additionally defends itself,
changing direction when something is in the way. A single pooled hypothesis would
therefore reject a rule that is working for one stratagem and not another, so the
four candidate rules below are fitted separately for each stratagem label.

Candidate rules (B = bearing from the player to where the beacon landed):

  along_from_behind   heading = B        the aircraft comes from behind the player
                                         and runs forward past them  (strafing run)
  along_from_front    heading = B + 180  the same line, approached from the far end
  perp_left           heading = B + 90   perpendicular, travelling one way
  perp_right          heading = B - 90   perpendicular, the other way

Which of perp_left/perp_right is the player's actual left depends on the engine's
axis handedness, which we have not established, so BOTH signs are tested and the
data decides. Do not read the names as more than labels until a run says which one
matches: that is itself one of the findings.

Obstacle avoidance means a large residual is NOT automatically evidence against a
rule - it may be one deflected call. Groups that contain both tight and loose calls
are labelled separately instead of being averaged into "does not fit".

Usage:
  python analyze_eagle_probe.py <probe.jsonl> [--json out.json] [--up auto|z|y]
  python analyze_eagle_probe.py <probe.jsonl> --stratagems "1=strafing_run,2=cluster"
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

# Mirror of the probe's STRATAGEM_OF: which stratagem a munition identity implies.
STRATAGEM_OF = {
    'eagle_airstrike': 'airstrike',
    'eagle_cluster': 'cluster',
    'eagle_napalm': 'napalm',
    'eagle_smoke': 'smoke',
    'eagle_gas': 'gas',
    'eagle_500kg': '500kg',
    'eagle_rocket': '110mm_rocket_pods',
    'eagle_gunpods': 'strafing_run',
    'eagle_base': 'strafing_run',
    'eagle_missile': 'air_to_air',
}

RULES = ('along_from_behind', 'along_from_front', 'perp_left', 'perp_right')
TIGHT_DEG = 20.0        # residuals at or below this count as "on the rule"

# Pre-registered expectations, so a run FALSIFIES them instead of being read against
# whatever happens to fit. Two sources, both describing the same two-family split:
#
#   player report (2026-10-07, current build)
#     strafing run  - along the player-to-beacon line, coming from behind
#     cluster bomb  - perpendicular, coming from the left
#   9game.cn guide (2024-02-24 - LAUNCH-ERA, so possibly stale; see README)
#     parallel family, from behind : strafing run, 110mm rocket pods, 500kg
#     perpendicular family         : airstrike, cluster, napalm, smoke
#
# The guide's perpendicular family is described as diving "from east to west" with
# the side depending on where the player faces, so WHICH of perp_left / perp_right
# matches is deliberately not pre-registered - that is itself a finding, and
# perp_left is only a label until a run says whether it is really the player's left.
#
# 'gas' is extrapolated: the gas airstrike did not exist in the 2024 guide, and it is
# an airstrike variant, so the perpendicular family is a guess, not a source.
EXPECTED_RULES = {
    'strafing_run': ('along_from_behind',),
    '110mm_rocket_pods': ('along_from_behind',),
    '500kg': ('along_from_behind',),
    'airstrike': ('perp_left', 'perp_right'),
    'cluster': ('perp_left', 'perp_right'),
    'napalm': ('perp_left', 'perp_right'),
    'smoke': ('perp_left', 'perp_right'),
    'gas': ('perp_left', 'perp_right'),
}
EXTRAPOLATED = ('gas',)


def expectation_for(stratagem):
    """Expected rules for a group label, or None when nothing is pre-registered.

    Labels can be compound (the strafing run spawns two munition identities), so any
    unrecognised part makes the whole group unregistered rather than half-checked.
    """
    parts = [p for p in (stratagem or '').split('+') if p]
    if not parts:
        return None
    found = []
    for part in parts:
        if part not in EXPECTED_RULES:
            return None
        found.extend(EXPECTED_RULES[part])
    return tuple(sorted(set(found)))


def predict_heading(rule, line_bearing):
    if rule == 'along_from_behind':
        return line_bearing
    if rule == 'along_from_front':
        return line_bearing + 180.0
    if rule == 'perp_left':
        return line_bearing + 90.0
    return line_bearing - 90.0


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
    """Per-unit track of (t, point, forward), keeping the query each unit came from.

    The source matters: an Eagle call records the aircraft AND its munitions, and a
    falling bomb is not the incoming direction. The caller must be able to prefer the
    aircraft rather than trusting whichever track happens to be longest.
    """
    out = {}
    for rec in records:
        if rec.get('kind') not in ('sample', 'idle_eagle'):
            continue
        for unit in rec.get(key) or []:
            if 'p' not in unit:
                continue
            entry = out.setdefault(unit['id'], {'src': None, 'rows': []})
            if entry['src'] is None:
                entry['src'] = unit.get('src')
            entry['rows'].append((rec.get('t', 0.0), unit['p'], unit.get('f')))
    for entry in out.values():
        entry['rows'].sort(key=lambda r: r[0])
    return out


def longest(entries):
    """The longest track from a list of track entries, or None."""
    usable = [e for e in entries if e['rows']]
    if not usable:
        return None
    return max(usable, key=lambda e: len(e['rows']))


def track_direction(rows, up):
    """Mean horizontal direction of travel and total horizontal distance."""
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


def stratagems_seen(records):
    """Stratagem families implied by the munition identities in this call."""
    families = set()
    for rec in records:
        for unit in rec.get('eagles') or []:
            family = STRATAGEM_OF.get(unit.get('src'))
            if family:
                families.add(family)
    return sorted(families)


def analyze_call(call_id, records, up, label=None):
    beacons = tracks(records, 'beacons', up)
    eagles = tracks(records, 'eagles', up)

    chosen_beacon = longest(list(beacons.values()))
    beacon_rows = chosen_beacon['rows'] if chosen_beacon else None
    if not beacon_rows or len(beacon_rows) < 2:
        return {'call': call_id, 'status': 'no usable beacon track'}

    origin = beacon_rows[0]
    settled = beacon_rows[-1]
    throw_bearing, _ = track_direction(beacon_rows, up)
    line_bearing = bearing(
        horizontal(settled[1], up)[0] - horizontal(origin[1], up)[0],
        horizontal(settled[1], up)[1] - horizontal(origin[1], up)[1])

    out = {
        'call': call_id,
        'status': 'ok',
        'stratagem': label or '+'.join(stratagems_seen(records)) or 'unknown',
        'throw_origin': origin[1],
        'beacon_landing': settled[1],
        'throw_bearing_deg': round(throw_bearing, 2) if throw_bearing is not None else None,
        'player_to_beacon_bearing_deg': round(line_bearing, 2),
        'samples': len(beacon_rows),
        'duration_s': round(beacon_rows[-1][0] - beacon_rows[0][0], 3),
    }
    for rule in RULES:
        out['predicted_%s_deg' % rule] = round(norm180(predict_heading(rule, line_bearing)), 2)

    # Prefer the aircraft. A falling bomb or rocket also gets recorded, and its track
    # is a descent, not the incoming direction - measuring that would silently report
    # a wrong axis. Fall back to a munition only when no aircraft track exists, and
    # say so, because a fallback reading deserves less trust.
    candidates = list(eagles.values())
    aircraft = [e for e in candidates if e['src'] == 'aircraft']
    chosen = longest(aircraft) or longest(candidates)
    eagle_rows = chosen['rows'] if chosen else None
    out['measured_from'] = chosen['src'] if chosen else None
    if chosen and chosen['src'] != 'aircraft':
        out['measured_from_warning'] = ('no aircraft track; measured from %s instead'
                                        % chosen['src'])
    if not eagle_rows or len(eagle_rows) < 2:
        out['eagle'] = 'not seen in this call'
        return out

    measured, travelled = track_direction(eagle_rows, up)
    out['eagle_samples'] = len(eagle_rows)
    out['eagle_first_seen_s'] = round(eagle_rows[0][0] - beacon_rows[0][0], 3)
    out['eagle_visible_for_s'] = round(eagle_rows[-1][0] - eagle_rows[0][0], 3)
    out['eagle_travel_m_horizontal'] = round(travelled, 2)
    out['eagle_forward_deg'] = forward_direction(eagle_rows, up)
    if measured is None:
        return out

    out['measured_heading_deg'] = round(measured, 2)
    errors = {}
    for rule in RULES:
        errors[rule] = round(norm180(measured - predict_heading(rule, line_bearing)), 2)
    out['rule_errors_deg'] = errors
    best = min(RULES, key=lambda r: abs(errors[r]))
    out['best_rule'] = best
    out['best_error_deg'] = abs(out['rule_errors_deg'][best])
    return out


def classify_verdict(usable):
    """Group the calls by stratagem and report which rule fits each one.

    Kept out of main() so the per-stratagem logic and the obstacle-avoidance branch
    are testable: the tests assert the label and the per-group rule, not the prose.

    Labels:
      'none'                   no call produced both tracks
      'rules_resolved'         every labelled group fits one rule tightly
      'rules_with_deflection'  every group fits a rule, but some calls are deflected
                               (the reported obstacle-avoidance signature)
      'rules_unresolved'       the residuals do not cluster on any rule
    """
    if not usable:
        return {'label': 'none', 'groups': {}, 'lines': [
            'VERDICT: no call produced both a beacon track and an Eagle track.',
            '         Nothing is decided yet - re-run with more calls, or turn on',
            '         FALLBACK_WORLD_SCAN if the Eagle was never listed.']}

    groups = {}
    for row in usable:
        groups.setdefault(row.get('stratagem') or 'unknown', []).append(row)

    lines = ['VERDICT over %d measurable call(s), grouped by stratagem:' % len(usable)]
    fallback = sorted(str(r.get('call')) for r in usable
                      if r.get('measured_from') not in (None, 'aircraft'))
    if fallback:
        lines += [
            '  WARNING: call(s) %s produced no aircraft track and were measured from a'
            % ', '.join(fallback),
            '           munition instead. A munition track is a descent, not an'
            ' incoming',
            '           direction, so those calls can report a wrong axis. Trust the'
            ' rest;',
            '           if every call did this, the aircraft query needs fixing first.',
        ]
    resolved, deflected, unresolved = [], [], []
    summary = {}

    for name in sorted(groups):
        rows = groups[name]
        tally = {}
        for rule in RULES:
            errs = [r['rule_errors_deg'][rule] for r in rows if 'rule_errors_deg' in r]
            if errs:
                tally[rule] = (sum(abs(e) for e in errs) / len(errs), errs)
        if not tally:
            lines.append('  %-22s no measured heading' % name)
            continue
        best_rule = min(tally, key=lambda r: tally[r][0])
        mean_abs, errs = tally[best_rule]
        tight = [e for e in errs if abs(e) <= TIGHT_DEG]
        loose = [e for e in errs if abs(e) > TIGHT_DEG]
        verdict = ('mixed' if (tight and loose) else
                   'fits' if not loose else 'loose')
        expected = expectation_for(name)
        if expected is None:
            agreement = 'unregistered'
        elif best_rule in expected:
            agreement = 'confirms'
        else:
            agreement = 'CONTRADICTS'
        if name in EXTRAPOLATED and agreement == 'confirms':
            agreement = 'confirms (extrapolated)'
        summary[name] = {
            'calls': len(rows),
            'best_rule': best_rule,
            'expected_rules': list(expected) if expected else None,
            'agreement': agreement,
            'mean_abs_error_deg': round(mean_abs, 1),
            'signed_errors_deg': [round(e, 1) for e in errs],
            'tight_calls': len(tight),
            'deflected_calls': len(loose),
            'verdict': verdict,
        }
        lines.append('  %-22s %-18s mean|err| %5.1f deg  signed %s  %s'
                     % (name, best_rule, mean_abs,
                        ', '.join('%.1f' % e for e in sorted(errs)), verdict))
        if expected is not None:
            if agreement.startswith('confirms'):
                lines.append('  %-22s expected %s -> %s'
                             % ('', '/'.join(expected), agreement))
            else:
                lines.append('  %-22s expected %s -> %s  (the pre-registered family'
                             ' is wrong for this stratagem)' % ('', '/'.join(expected),
                                                                agreement))
        if verdict == 'mixed':
            deflected.append(name)
        elif verdict == 'fits':
            resolved.append(name)
        else:
            unresolved.append(name)

    confirmed = sorted(n for n in summary if summary[n]['agreement'].startswith('confirms'))
    contradicted = sorted(n for n in summary if summary[n]['agreement'] == 'CONTRADICTS')
    unregistered = sorted(n for n in summary if summary[n]['agreement'] == 'unregistered')
    if confirmed or contradicted:
        lines.append('')
        lines.append('  Pre-registered families: %d confirmed, %d contradicted, '
                     '%d unregistered'
                     % (len(confirmed), len(contradicted), len(unregistered)))
        if confirmed:
            lines.append('    confirmed   : %s' % ', '.join(confirmed))
        if contradicted:
            lines.append('    CONTRADICTED: %s  <- the reported family does not hold '
                         'for these' % ', '.join(contradicted))

    if deflected:
        lines += [
            '',
            '  -> DEFLECTION SIGNATURE in: %s' % ', '.join(deflected),
            '     Those groups fit the rule on some calls and miss badly on others.',
            '     The Eagle is reported to avoid obstacles, so ask the player which',
            '     calls were aimed toward cover before reading the misses as evidence',
            '     against the rule - the probe cannot see terrain.',
        ]

    if resolved and not deflected and not unresolved:
        label = 'rules_resolved'
        lines += [
            '',
            '  -> Every stratagem fits one rule tightly. That is the outcome a',
            '     prediction mod wants: the direction is computable at throw time',
            '     from the player and the beacon, per stratagem. Note which rule each',
            '     name resolved to - and confirm on a second mission before building.',
        ]
    elif deflected:
        label = 'rules_with_deflection'
        lines += [
            '',
            '  -> The per-stratagem rules look real, with a deflection on top. A',
            '     nominal-axis prediction mod would be right in the open and wrong',
            '     near cover; reading the live aircraft instead returns the',
            '     post-avoidance heading and is unaffected.',
        ]
    else:
        label = 'rules_unresolved'
        lines += [
            '',
            '  -> No rule fits. Look at eagle_forward_deg and at the idle_eagle',
            '     samples: the heading may follow the aircraft\'s own state, which',
            '     means reading the aircraft rather than computing from geometry.',
        ]

    leads = [r['eagle_first_seen_s'] for r in usable if 'eagle_first_seen_s' in r]
    if leads:
        lines.append('')
        lines.append('  Lead time (first sighting -> beacon settled): %.2f..%.2f s'
                     % (min(leads), max(leads)))
    return {'label': label, 'groups': summary, 'lines': lines}


def parse_labels(text):
    """'1=strafing_run,2=cluster' -> {'1': 'strafing_run', '2': 'cluster'}"""
    out = {}
    if not text:
        return out
    for chunk in text.split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if '=' not in chunk:
            raise SystemExit('--stratagems entries look like 1=cluster; got %r' % chunk)
        call, name = chunk.split('=', 1)
        out[call.strip()] = name.strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl')
    ap.add_argument('--json', default=None)
    ap.add_argument('--up', default='auto', choices=('auto', 'x', 'y', 'z'))
    ap.add_argument('--stratagems', default=None,
                    help='override or supply per-call stratagem names, '
                         'e.g. "1=strafing_run,2=cluster"')
    args = ap.parse_args()

    records = load(args.jsonl)
    if not records:
        print('no records in %s' % args.jsonl)
        return 1

    labels = parse_labels(args.stratagems)
    up, up_why = choose_up(records, args.up)
    calls = sorted({r['call'] for r in records
                    if r.get('kind') in ('sample', 'call_begin') and r.get('call')})
    caps = [r for r in records if r.get('kind') == 'capabilities']
    stops = [r for r in records if r.get('kind') == 'stopped']
    seen = [r for r in records if r.get('kind') == 'call_stratagem']

    print('records            : %d' % len(records))
    print('vertical axis      : %s  (%s)' % (up, up_why))
    if caps:
        print('stingray on load   : %s' % caps[0].get('note'))
    print('idle eagle samples : %d  (aircraft visible between calls?)'
          % len([r for r in records if r.get('kind') == 'idle_eagle']))
    if seen:
        print('stratagems named by the probe: %s'
              % ', '.join(sorted({r.get('note', '?') for r in seen})))
    if stops:
        print('probe note         : %s' % stops[0].get('note'))
    print('calls detected     : %d' % len(calls))

    results = []
    for call_id in calls:
        subset = [r for r in records if r.get('call') == call_id]
        results.append(analyze_call(call_id, subset, up, labels.get(str(call_id))))

    print()
    for row in results:
        print('--- call %s  [%s] ---' % (row['call'], row.get('stratagem', '?')))
        if row.get('status') != 'ok':
            print('   %s' % row.get('status'))
            continue
        print('   player->beacon bearing : %.1f deg'
              % row['player_to_beacon_bearing_deg'])
        if 'measured_heading_deg' not in row:
            print('   measured heading       : %s' % row.get('eagle'))
            continue
        print('   MEASURED heading       : %.1f deg' % row['measured_heading_deg'])
        source = row.get('measured_from')
        print('   measured from          : %s%s'
              % (source or '?',
                 '' if source == 'aircraft'
                 else '   <-- NOT the aircraft; treat this axis with care'))
        for rule in RULES:
            mark = '  <- best' if rule == row.get('best_rule') else ''
            print('     %-18s predict %7.1f  err %7.1f%s'
                  % (rule, row['predicted_%s_deg' % rule],
                     row['rule_errors_deg'][rule], mark))
        print('   eagle first seen at    : +%.2fs after the throw' % row['eagle_first_seen_s'])
        print('   eagle visible for      : %.2fs, travelling %.1fm'
              % (row['eagle_visible_for_s'], row['eagle_travel_m_horizontal']))
        if row.get('eagle_forward_deg') is not None:
            print('   aircraft forward vector: %.1f deg' % row['eagle_forward_deg'])

    usable = [r for r in results if 'measured_heading_deg' in r]
    print()
    verdict = classify_verdict(usable)
    for line in verdict['lines']:
        print(line)

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({'vertical_axis': up, 'axis_choice': up_why,
                       'verdict': verdict['label'], 'groups': verdict['groups'],
                       'calls': results}, fh, indent=1)
        print('\nwrote %s' % args.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
