# 45-degree flanged pipe elbow.  2D sketches:
#   path1, path2 -- pipe centre-line (path2 pokes 1 mm out at both ends, for the bore)
#   sec1, sec2   -- pipe Ø130 and bore Ø88
#   flange, holes -- 255 x 255 flange outline (R38 corners) and its 4 x Ø32 holes
p1 = rot('x90', path1)
p2 = rot('x90', path2)
pipe = swp(sweep_sec2path(sec1, p1))
bore = swp(sweep_sec2path(sec2, p2))

# each flange extruded on its own (two copies of one shape share faces, and
# the turned copy then exports with cracks)
f1 = difference(linear_extrude(flange, 37), *[translate([0, 0, -1], linear_extrude(c, 39)) for c in holes])
f2 = difference(linear_extrude(flange, 37), *[translate([0, 0, -1], linear_extrude(c, 39)) for c in holes])
f1 = translate([0, 0, -37], f1)                          # top flange
f2 = translate([65.9, 0, -196.1], rot('y135', f2))       # second flange, at the end of the bend

part = union([pipe, f1, f2])
part = difference(part, bore)
e2 = [part.edges()[i] for i in [70, 21]]  # <- probe list tool: e2
part = fillet(part, e2, 10)  # <- probe fillet tool: e2
e1 = [part.edges()[i] for i in [75, 73, 44, 43]]  # <- probe list tool: e1
part = fillet(part, e1, 15)  # <- probe fillet tool: e1
show(part)
