s1=swp(rot('y90',translate([0,0,-45],linear_extrude(circle(15),90))))
pl1=swp_surf(translate([45,0,0],plane_from_equation([0,-1,0,0])))
s2=swp(sweep_placed_sec2path(sec1_3d,path1_3d))
s3=swp(surface_line_vector(sec2_3d,[0,5,0],1))
s4=union([s1,s2,s3])
e1 = [s4.edges()[i] for i in [44, 45, 46]]  # <- probe list tool: e1
f_e1 = fillet_by_offset(e1, s4, s4, 2, -2, auto_dir=0, as_solid=1)  # <- probe offset fillet tool: e1
s4 = union([s4, swp(f_e1)])  # <- probe offset fillet union: e1
s5=swp(surface_line_vector(sec3_3d,[0,10,0],1))
s6=difference(s4,s5)
c1=cylinder(r=4,h=40,center=1)
c2=translate([0,0,5],cylinder(r=7.5,h=20))
c3=translate([0,0,-25],cylinder(r=7.5,h=20))
s7=difference(s6,c1,c2,c3)
show(s7)
