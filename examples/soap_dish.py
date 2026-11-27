# ---------------------------------------------------------------
# Draining soap dish: a perforated insert with spikes that hold the
# soap up off its floor, resting on posts inside a tray that collects
# the water.  Both parts print flat side down with no supports.
#
# The two shells are each one prism(): a 2D section (the outline seen
# from above) swept along a 2D path (the wall profile, x = offset from
# the outline, y = height).  All the edge rounding is corner radii on
# those two 2D sketches.  Every size below is a parameter.
# ---------------------------------------------------------------

# insert (the part the soap sits on)
L = 100        # outer length (x)
W = 70         # outer width (y)
H = 15         # height (floor underside to rim)
R = 8          # corner radius seen from above (outside)
wall = 2       # wall thickness
floor_t = 2    # floor thickness

# spikes (the soap rests on their tips)
pitch = 10     # spacing between spikes, both directions
margin = 6     # gap from the inside wall to the outermost spikes
spike_h = 6    # height above the floor
spike_r1 = 2.2 # radius at the base
spike_r2 = 0.9 # radius at the tip
spike_tip_r = 0.8  # rounding of the tip (keep under spike_r2)

# drainage holes (centred between every 4 spikes)
hole_d = 4

# tray (collects the water)
gap = 0.6          # clearance around the insert
tray_wall = 2
tray_floor = 2
post_h = 5         # insert sits this high above the tray floor (water space)
post_r = 3
post_inset = 10    # post centre distance from the insert's outside edge
post_top_r = 0.6   # rounding of the post tops
tray_rim = 9       # tray wall height above the insert's underside
notch_r = 9        # finger notches in the short walls (0 = none)

# edge rounding (corner radii in the wall-profile sketches)
r_rim = 0.8        # top rims, inside and outside (keep under wall/2)
r_inner = 1.5      # where the floor meets the walls, inside
r_bottom = 1.0     # outside bottom edges

explode = 0        # >0 lifts the insert out of the tray, for a clearer view


def rrect(l, w, r):
    """2D rounded rectangle centred on the origin (the outline seen from above)"""
    return cr2dt([[-l/2, -w/2, r], [l, 0, r], [0, w, r], [-l, 0, r]], 10)


def shell(l, w, r, h, t_wall, t_floor):
    """open-topped rounded box as ONE prism: the outline rrect(l, w, r)
    swept along the wall profile below, whose corner radii are the
    fillets (bottom edge, rim inside and out, floor-to-wall)"""
    c0 = (l if l < w else w) / 2 - 1   # the profile runs in to here (the floor)
    profile = corner_radius(pts1([
        [-c0, 0],                    # floor underside, from the middle
        [c0, 0, r_bottom],           # outside bottom edge
        [0, h, r_rim],               # up the outside wall to the rim
        [-t_wall, 0, r_rim],         # across the rim
        [0, -(h - t_floor), r_inner],  # down the inside wall to the floor
        [-(c0 - t_wall), 0],         # floor top, back to the middle
    ]), 10)
    return swp(prism(rrect(l, w, r), profile))


# ---------------- insert ----------------
dish = shell(L, W, R, H, wall, floor_t)

# spike grid, centred in the pocket
Li, Wi = L - 2*wall, W - 2*wall
nx = int((Li - 2*margin) // pitch) + 1
ny = int((Wi - 2*margin) // pitch) + 1
x0 = -(nx - 1) * pitch / 2
y0 = -(ny - 1) * pitch / 2
spike = swp(cylinder(r1=spike_r1, r2=spike_r2, h=spike_h + 0.5))
spike = fillet(spike, [e for e in spike.edges() if abs(e.position_at(0.5).Z - (spike_h + 0.5)) < 1e-3], spike_tip_r)
spikes = [translate([x0 + i*pitch, y0 + j*pitch, floor_t - 0.5], spike)
          for i in range(nx) for j in range(ny)]

# holes between the spikes, right through the floor
hole = swp(cylinder(r=hole_d/2, h=floor_t + 2))
holes = [translate([x0 + (i + 0.5)*pitch, y0 + (j + 0.5)*pitch, -1], hole)
         for i in range(nx - 1) for j in range(ny - 1)]

dish = union([dish] + spikes)
dish = difference(dish, group(holes))   # all holes in ONE cut (one at a time took ~75 s)

# ---------------- tray ----------------
Lt_in, Wt_in, Rt_in = L + 2*gap, W + 2*gap, R + gap
Lt, Wt, Rt = Lt_in + 2*tray_wall, Wt_in + 2*tray_wall, Rt_in + tray_wall
tray_h = tray_floor + post_h + tray_rim
z_tray = -post_h - tray_floor          # the insert's underside is at z = 0
tray = translate([0, 0, z_tray], shell(Lt, Wt, Rt, tray_h, tray_wall, tray_floor))

# posts on the tray floor, carrying the insert
post = swp(cylinder(r=post_r, h=post_h + 0.5))
post = fillet(post, [e for e in post.edges() if abs(e.position_at(0.5).Z - (post_h + 0.5)) < 1e-3], post_top_r)
px, py = L/2 - post_inset, W/2 - post_inset
posts = [translate([sx*px, sy*py, -post_h - 0.5], post) for sx in (-1, 1) for sy in (-1, 1)]
tray = union([tray] + posts)

# finger notches: a cylinder across each short wall, centred on the rim
if notch_r > 0:
    z_top = z_tray + tray_h
    notch = rot('y90', swp(cylinder(r=notch_r, h=Wt / 2)))
    tray = difference(tray,
                      translate([Lt/2 - Wt/4, 0, z_top], notch),
                      translate([-Lt/2 - Wt/4, 0, z_top], notch))

dish = translate([0, 0, explode], dish)
e1 = [tray.edges()[i] for i in [67]]  # <- probe list tool: e1
tray = fillet(tray, e1, 0.8)  # <- probe fillet tool: e1
e2 = [tray.edges()[i] for i in [64]]  # <- probe list tool: e2
tray = fillet(tray, e2, 0.8)  # <- probe fillet tool: e2
show(color(dish, 'lightblue'), color(tray, 'white', alpha=0.45))
