# ---------------------------------------------------------------
# Angle bracket with rib (from the drawing)
# x along the flat leg (0 = inside corner of the bend), y across
# (0 = centre), z up (0 = underside of the flat leg)
# ---------------------------------------------------------------

t = 10                # plate thickness
W = 44                # plate width
bend = 120            # inside angle between the two legs (degrees)
flat_len = 80         # flat leg, from the inside corner to its rounded end
end_r = W / 2         # full round end of the flat leg (R22)
leg_len = 47.77       # raised leg, along its outside face
corner_r = 10         # the raised leg's two top corners (2x R10)

slot_c = 25           # slot: centre-to-centre length
slot_w = 12           # slot width (2x R6)

hole_d = 6            # holes in the raised leg
cb_d = 12             # counterbore on the inside face
cb_depth = 3
hole_in = 10          # hole centres: this far from the top end and from each side

rib_w = 6             # central rib
rib_foot = 25         # where the rib meets the flat leg (from the inside corner)

e = 0.5               # small overlaps so no two pieces share a face

# --- geometry of the bend (x-z plane) ---
a = radians(180 - bend)                    # raised leg's slope from horizontal (60 deg)
u = array([-cos(a), sin(a)])               # up along the raised leg
n = array([-sin(a), -cos(a)])              # its outside-face normal
p_in = array([0, t])                       # inside corner of the bend
q = p_in + t * n                           # a point on the leg's outside face
p_out = q + u * (-q[1] / u[1])             # outside corner: that face meets the underside z = 0
top_out = p_out + leg_len * u              # top end, outside face
top_in = top_out - t * n                   # top end, inside face
s_top = norm(top_in - p_in)                # inside-face length of the raised leg


def extrude_y(pts, w, r_seg=10):
    """x-z profile (corner radius as 3rd value), extruded w across y, centred"""
    s = solid_line_vector(cr2d(pts, r_seg), [0, 0, w])
    return translate([0, w / 2, 0], rot('x90', s))


def extrude_z(pts, z0, h, r_seg=10):
    """x-y outline (corner radius as 3rd value), extruded h up from z0"""
    return translate([0, 0, z0], solid_line_vector(cr2d(pts, r_seg), [0, 0, h]))


# --- bent plate: side profile across the full width ---
x_end = flat_len
plate = extrude_y([
    [p_out[0], p_out[1], 0],
    [x_end, 0, 0],
    [x_end, t, 0],
    [p_in[0], p_in[1], 0],
    [top_in[0], top_in[1], 0],
    [top_out[0], top_out[1], 0],
], W)

# round end of the flat leg (plan view): keep x <= centre of R22, plus the R22 disc
xc = flat_len - end_r
keep = union([
    translate([-100, -W, -50], box([100 + xc, 2 * W, 200])),
    translate([xc, 0, -50], swp(cylinder(r=end_r, h=200))),
])
plate = intersection(plate, keep)

# R10 on the raised leg's two top corners: the edges running through the
# thickness at the top end, picked by position
corner_mid = (top_out + top_in) / 2
corner_edges = []
for ed in plate.edges():
    m = ed.position_at(0.5)
    if abs(m.X - corner_mid[0]) < 0.2 and abs(m.Z - corner_mid[1]) < 0.2 and abs(abs(m.Y) - W / 2) < 0.2:
        corner_edges.append(ed)
plate = fillet(plate, corner_edges, corner_r)

# --- rib: a triangle between the two legs, sunk a hair into both ---
rib_top = p_in + (s_top - e) * u + e * n           # just under the top end, sunk into the leg
rib = extrude_y([
    [p_in[0] - e, p_in[1] - e, 0],
    [rib_foot, p_in[1] - e, 0],
    [rib_top[0], rib_top[1], 0],
], rib_w)
part = union([plate, rib])

# --- cuts: slot in the flat leg, counterbored holes in the raised leg ---
slot = extrude_z([[xc - slot_c - slot_w / 2, -slot_w / 2, slot_w / 2 - 0.001],
                  [xc + slot_w / 2, -slot_w / 2, slot_w / 2 - 0.001],
                  [xc + slot_w / 2, slot_w / 2, slot_w / 2 - 0.001],
                  [xc - slot_c - slot_w / 2, slot_w / 2, slot_w / 2 - 0.001]], -1, t + 2)

def tube(d, length, start, direction):
    """cylinder of diameter d, `length` long, from point `start` (x, z) in
    `direction` (x, z) -- rot('y b') turns +z to (sin b, 0, cos b)"""
    b = degrees(arctan2(direction[0], direction[1]))
    return rot(f'y{b}', swp(cylinder(d=d, h=length))), start


h_c = p_in + (s_top - hole_in) * u           # hole centre on the inside face
cuts = [slot]
for sy in (-1, 1):
    yy = sy * (W / 2 - hole_in)
    # through hole: from 1 mm outside the inside face, right through the leg
    c, st = tube(hole_d, t + 2, h_c - n * 1, n)
    cuts.append(translate([st[0], yy, st[1]], c))
    # counterbore: Ø12, cb_depth into the leg from the inside face
    c, st = tube(cb_d, cb_depth + 1, h_c - n * 1, n)
    cuts.append(translate([st[0], yy, st[1]], c))
part = difference(part, group(cuts))
part = part.clean()

show(part)
