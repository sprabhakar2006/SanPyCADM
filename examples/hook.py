s1=swp(sphere(20))
pl1=swp_surf(plane_from_equation([0,0,1,0]))
pl2=swp_surf(plane_from_equation([0,0,1,4]))
s2=split(s1,pl1,'top')
s3=surface_line_vector(sec1_3d,[0,0,20])
s4=difference(s2,s3)
e1 = [s4.edges()[i] for i in [4]]  # <- probe list tool: e1
s4 = fillet(s4, e1, 8)  # <- probe fillet tool: e1
e2 = [s4.edges()[i] for i in [0, 1, 3, 2]]  # <- probe list tool: e2
e2=sample_curve(wire_from_edges(e2),200)
e2=remove_line_beyond_plane(e2,[0,1,0,0])
pl3=swp_surf(plane_from_equation([0,-1,0,0]))
s5=surface_line_vector(sec2_3d,[0,-30,0],1)
s6=difference(s4,s5)
e3 = [s6.edges()[i] for i in [2]]  # <- probe list tool: e3
s6 = fillet(s6, e3, 1.5)  # <- probe fillet tool: e3
e4 = [s6.edges()[i] for i in [20, 18, 17, 15, 22]]
f_e4 = fillet_by_offset(e4, s6, 1.4, as_solid=1)  # <- probe offset fillet tool: e4
s6 =resize_solid( difference(s6, f_e4),[40,30,15])  # <- probe offset fillet union: e4
show(s6)