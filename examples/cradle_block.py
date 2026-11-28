# ---------------------------------------------------------------
# Cradle block (from the 3-view drawing)
# x = length (front view width, 130), y = depth (side view width, 90),
# z = height (100).  Origin at the front-left-bottom corner.
# ---------------------------------------------------------------

L = 130               # length (x)
D = 90                # depth (y)
H = 100               # overall height
base_h = 40           # base block height
arch_r = 25           # arch under the base (side view), running along x

# uprights: two slabs, front-view profile, 20 thick, 20 apart
up_t = 20             # slab thickness (y)
slot_w = 20           # gap between them (y)
slot_bottom = 30      # the gap is cut down to here (70 deep from the top)
vert = 10             # uprights rise straight for this much above the base, then slope
flat = 10             # flat on top either side of the cradle
cradle_r = 30         # cradle radius, centred at the top

# through hole and the two pockets
hole_d = 30
hole_z = 50
pocket_w = 50         # pockets in the front and back faces (x)
pocket_d = 25         # their depth into the part (y)
pocket_z = 25         # their bottom

xm, ym = L / 2, D / 2
y_up = ym - slot_w / 2 - up_t          # front face of the front upright


def extrude_y(pts, y0, t):
    """a front-view (x-z) profile, corner radius as 3rd value, extruded
    t along y starting at y0"""
    s = solid_line_vector(cr2d(pts, 10), [0, 0, t])
    return translate([0, y0 + t, 0], rot('x90', s))


def extrude_x(pts, x0, t):
    """a side-view (y-z) profile extruded t along x starting at x0"""
    s = solid_line_vector(cr2d(pts, 10), [0, 0, t])
    return translate([x0, 0, 0], rot('x90z90', s))


# base, with the arch along x
base = box([L, D, base_h])
arch = extrude_x([[ym + c * arch_r, s * arch_r, 0] for c, s in
                  zip(cos(linspace(0, 2 * pi, 64)[:-1]), sin(linspace(0, 2 * pi, 64)[:-1]))], -1, L + 2)

# uprights: front-view profile (trapezoid with the R30 cradle), as one
# block across both slabs; the slot between them is cut afterwards
a = linspace(pi, 2 * pi, 33)
cradle = [[xm + cradle_r * cos(t), H + cradle_r * sin(t), 0] for t in a]   # left to right, dipping down
x_top = xm - cradle_r - flat
profile = ([[0, base_h - 1, 0], [L, base_h - 1, 0], [L, base_h + vert, 0],
            [L - x_top, H, 0], [xm + cradle_r, H, 0]] + cradle[::-1][1:-1] +
           [[xm - cradle_r, H, 0], [x_top, H, 0], [0, base_h + vert, 0]])
uprights = extrude_y(profile, y_up, 2 * up_t + slot_w)

part = union([base, uprights])

# cuts: arch, slot between the uprights, Ø30 hole (along y), front and back pockets
slot = translate([-1, ym - slot_w / 2, slot_bottom], box([L + 2, slot_w, H]))
hole = translate([xm, -1, hole_z], rot('x-90', swp(cylinder(d=hole_d, h=D + 2))))
pockets = [translate([xm - pocket_w / 2, y0, pocket_z], box([pocket_w, pocket_d + 1, H]))
           for y0 in (-1, D - pocket_d)]
part = difference(part, group([arch, slot, hole] + pockets))
part = part.clean()

show(part)
