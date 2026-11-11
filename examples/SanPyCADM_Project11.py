s1=swp(linear_extrude(sec1,45))
s2=swp(linear_extrude(sec2,45))
s3=difference(s1,s2)
pl1=swp_surf(plane_from_equation([1,0,0,0]))
xs=split(s3,pl1,'bottom')
pl2=swp_surf(plane_from_equation([0,-1,0,0]))
s4=swp(surface_line_vector(sec3_3d,[60,0,0],1))
s5=union([s3,s4])
e1 = [s5.edges()[i] for i in [6, 4]]  # <- probe list tool: e1
s5 = fillet(s5, e1, 5)  # <- probe fillet tool: e1
e2 = [s5.edges()[i] for i in [40, 33, 13, 17]]  # <- probe list tool: e2
s5 = fillet(s5, e2, 10)  # <- probe fillet tool: e2
s6=[swp(translate([0,0,1],linear_extrude(p,-7))) for p in sec4_3d]
s7=[swp(surface_line_vector(p,[0,7,0],1)) for p in sec5_3d]
s8=difference(s5,*s6,*s7)
show(s8)