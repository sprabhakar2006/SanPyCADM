# ---------------------------------------------------------------
# Split pipe clamp (from the drawing with SECTION A-A)
# y = along the tube (0 = back face, 50 = front face)
# x = across (0 = centre, the slot plane), z = up (0 = tube axis)
# ---------------------------------------------------------------

od = 50               # tube outside diameter
bore = 35             # tube bore
length = 50           # tube length (y)

lug_d = 15            # lug (ear) on top: round-topped, across the slot
lug_len = 40          # its length (x)
lug_from_back = 5     # it starts this far from the back face
lug_z = 28            # its axis (and hole centre) above the tube axis
lug_hole = 7.5        # bolt hole through the lug (along x)
slot_w = 5            # the split, through the lug and the top of the tube wall

chamfer_y = 25        # the 45-degree cut-back of the front starts this far from
                      # the back at the top of the tube, reaching the front face
                      # at axis height
chamfer_r = 12        # where it blends into the front face

R, r = od / 2, bore / 2
e = 0.5               # small overlaps so no two pieces share a face


def along_x(pts_yz, x0, lx):
    """a y-z profile (corner radius as 3rd value), extruded lx along x from x0"""
    s = solid_line_vector(cr2d(pts_yz, 10), [0, 0, lx])
    return translate([x0, 0, 0], rot('x90z90', s))


# The round parts are true cylinders and the lug block a box: shapes built
# from point-sampled circles become approximate B-spline surfaces, and fillets
# then fail on the edges between them (e.g. where the lug meets the tube).

# tube body (solid for now; the bore is cut at the end)
body = rot('x-90', swp(cylinder(r=R, h=length)))           # exact cylinder (along +y)

# lug: a U shape across x -- a block from inside the tube wall up to its
# axis, with the full round (R7.5) on top, its sides running straight
# into the round
lug_y0 = lug_from_back
lug = translate([-lug_len / 2, lug_y0, R - 10], box([lug_len, lug_d, lug_z - (R - 10)]))
lug = union([lug, translate([-lug_len / 2, lug_y0 + lug_d / 2, lug_z], rot('y90', swp(cylinder(d=lug_d, h=lug_len))))])

part = union([body, lug])

# 45-degree cut-back of the front (side profile, y-z), with R12 into the front face
keep = along_x([
    [-10, -R - 10, 0],
    [length, -R - 10, 0],
    [length, 0, chamfer_r],                      # front face up to axis height, R12 here
    [chamfer_y, R, 0],                           # 45 degrees up to the top of the tube...
    [chamfer_y, lug_z + lug_d, 0],               # ...and clear of everything above it
    [-10, lug_z + lug_d, 0],
], -R - 10, 2 * R + 20)
part = intersection(part, keep)

# cuts: bore, slot (through the lug and the top of the wall), lug hole
bore_cut = translate([0, -1, 0], rot('x-90', swp(cylinder(r=r, h=length + 2))))
slot = translate([-slot_w / 2, -1, 0], box([slot_w, length + 2, lug_z + lug_d]))
hole = translate([-lug_len / 2 - 1, lug_y0 + lug_d / 2, lug_z], rot('y90', swp(cylinder(d=lug_hole, h=lug_len + 2))))
part = difference(part, group([bore_cut, slot, hole]))
part = part.clean()

show(part)
