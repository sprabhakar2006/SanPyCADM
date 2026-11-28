# Gear shaft.  2D sketches (edit them in the 2D Sketch panel):
#   shaft -- half-profile from SECTION B-B: x = radius, y = along the axis
#   gear  -- 18-tooth gear outline (module 2), centred on the origin
# Built along z, then laid along x at the end.

gear_z0, gear_w = 27, 15      # gear position and width along the axis
sq, sq_z0 = 12, 70            # square end: 12 x 12 from here to the end
L = 92                        # overall length
ch = 1                        # ALL CHAMFER 1x45

body = rotate_extrude(polygon(shaft))

# square end: keep the round part up to sq_z0, then only the 12 x 12 square
keep = union([translate([0, 0, -1], swp(cylinder(r=30, h=sq_z0 + 1))),
               translate([-sq / 2, -sq / 2, sq_z0 - 1], box([sq, sq, L - sq_z0 + 2]))])
body = intersection(body, keep)

# gear: the sketch extruded; its tooth ends chamfered 1x45 by intersecting
# with a Ø40 disc whose two rims are chamfered
teeth = translate([0, 0, gear_z0], swp(linear_extrude(gear, gear_w)))
disc = translate([0, 0, gear_z0], swp(cylinder(r=20, h=gear_w)))
disc = chamfer(disc, disc.edges(), ch)
part = union([body, intersection(teeth, disc)])

# Detail C: centre hole in the end -- 60 deg countersink to Ø3, pilot Ø1.15 x 3
cs = translate([0, 0, L - 1.6], swp(cylinder(r1=0.575, r2=2.1, h=2.64)))
pilot = translate([0, 0, L - 3], swp(cylinder(d=1.15, h=3.5)))
part = difference(part, group([cs, pilot]))

part = rot('y90', part)       # lay it along x
show(part)
