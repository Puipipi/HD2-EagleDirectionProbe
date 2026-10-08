"""Which axis is UP? This has been assumed since the first version and never checked.

If z is not the vertical axis, the ground strip is a vertical wall rather than a band on the
ground, and the air corridor is drawn in the wrong plane - which would explain a corridor that
the player cannot find.

Three independent tests on data already captured, all of which should agree if z is up:

  1. GROUND OBJECTS. A landed beacon lies on the terrain. If z is up, its z range across different
     map positions is terrain relief (metres); its x and y ranges are how far apart the throws
     were (tens to hundreds of metres).
  2. THE AIRCRAFT. A plane flying a pass moves far horizontally and little vertically, so the
     total variation along the up axis should be the smallest of the three.
  3. ALTITUDE SEPARATION. The aircraft must be above the ground objects along whichever axis is
     up.
"""
import collections
import glob
import json
import os

LOGS = os.path.expandvars(r"%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs")


def load(path):
    recs = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def axis_stats(points):
    """Per-axis range and total variation (sum of |delta| along that axis)."""
    if not points:
        return None
    out = []
    for k in range(3):
        vals = [p[k] for p in points]
        var = sum(abs(points[i + 1][k] - points[i][k]) for i in range(len(points) - 1))
        out.append((max(vals) - min(vals), var))
    return out


def main():
    files = [f for f in glob.glob(os.path.join(LOGS, "EagleDirectionProbe-*.jsonl"))
             if os.path.getsize(f) > 20000]
    files.sort(key=os.path.getmtime)

    for path in files:
        recs = load(path)
        samples = [r for r in recs if r.get("kind") in ("sample", "idle_eagle")]
        beacons = [u["p"] for r in samples for u in (r.get("beacons") or []) if "p" in u]
        eagles = [u["p"] for r in samples for u in (r.get("eagles") or []) if "p" in u]
        if len(beacons) < 5 or len(eagles) < 5:
            continue
        names = "xyz"
        print("=" * 74)
        print(os.path.basename(path))
        print("=" * 74)

        # TEST A: altitude separation. A plane is far above objects lying on the ground, so the
        # up axis is the one where the two sets are furthest apart in the mean. This is the
        # decisive test and it does not depend on how the aircraft manoeuvres.
        mean_b = [sum(p[k] for p in beacons) / len(beacons) for k in range(3)]
        mean_e = [sum(p[k] for p in eagles) / len(eagles) for k in range(3)]
        print("  mean separation between ground objects and the aircraft:")
        for k in range(3):
            print("    %s: %9.1f" % (names[k], abs(mean_e[k] - mean_b[k])))
        up = max(range(3), key=lambda k: abs(mean_e[k] - mean_b[k]))

        # TEST B: terrain relief. A landed beacon is constrained by the ground, so the up axis is
        # the one whose spread across different throws is smallest.
        spread = [max(p[k] for p in beacons) - min(p[k] for p in beacons) for k in range(3)]
        print("  ground-object spread (terrain relief on the up axis):")
        for k in range(3):
            print("    %s: %9.1f" % (names[k], spread[k]))
        smallest = min(range(3), key=lambda k: spread[k])

        print("  -> altitude separation says %s ; terrain relief says %s" % (names[up], names[smallest]))
        print("  -> %s" % ("CONSISTENT" if up == smallest else "INCONSISTENT"))
        print()


if __name__ == "__main__":
    main()
