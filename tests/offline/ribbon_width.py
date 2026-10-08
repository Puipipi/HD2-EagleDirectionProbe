"""How many pixels wide is the corridor actually, at the distances that matter?

This is the check I should have run before shipping "a ribbon of parallel strands". The strand
offset scales with distance, so the on-screen width is roughly constant - but constant at what?
The arithmetic is simple and I never did it:

    horizontal pixels per metre at distance D  =  screen_width / (2 * D * tan(hfov/2))

At 1920 px and a 90 degree horizontal field of view that is 1920 / (2 * D * 1.0) = 960 / D.
So 1 m at 200 m spans 4.8 px, and at 900 m it spans 1.1 px.

The old setting was STRAND_STEP_PER_M = 0.0012 with 3 strands: at 200 m the whole ribbon was
2 * 0.0012 * 200 = 0.48 m, which is about 2 px. Two pixels is a line, not a band - which is
exactly what the player reported.
"""
import math

SCREEN_W = 1920
HFOV_DEG = 90.0
TAN_HALF = math.tan(math.radians(HFOV_DEG / 2))


def px_per_m(dist):
    return SCREEN_W / (2 * dist * TAN_HALF)


def ribbon_px(dist, step_per_m, strands):
    width_m = step_per_m * max(dist, 15) * (strands - 1)
    return width_m * px_per_m(dist)


def report(label, step_per_m, strands):
    print("%-28s" % label, end="")
    for dist in (50, 100, 200, 500, 900):
        print("  %5.1fpx@%-4dm" % (ribbon_px(dist, step_per_m, strands), dist), end="")
    print()


print("=" * 96)
print("Ribbon width on screen (1920 px wide, 90 deg horizontal field of view)")
print("=" * 96)
report("old: 0.0012 x 3 strands", 0.0012, 3)
report("new air: 0.0022 x 5 strands", 0.0022, 5)
report("new ground edges: 0.0022 x 5", 0.0022, 5)
print()
print("For reference, a single line is about 1 px at every distance.")
print("A dense hatch is the other way to read as an area: 47 cross ticks over 280 m is one")
print("pixel per line but reads as a filled ladder, and costs no extra width at all.")
