
s1=swp(linear_extrude(sec1,10))
s2=swp(translate([0,0,2],linear_extrude(sec2,8)))
s3=difference(s1,s2)
s4=[translate([0,0,-0.5],linear_extrude(p,11)) for p in sec3]
s5=difference(s3, *[swp(p) for p in s4])
e1 = [s5.edges()[i] for i in [47, 49, 50, 48, 46, 44, 42, 40, 39, 41, 43, 45]]  # <- probe list tool: e1
s5 = fillet(s5, e1, 1)  # <- probe fillet tool: e1
e2 = [s5.edges()[i] for i in [91, 96, 100, 104, 108, 112, 113, 109, 105, 101, 97, 93]]  # <- probe list tool: e2
s5 = fillet(s5, e2, 1)  # <- probe fillet tool: e2
e3 = [s5.edges()[i] for i in [59, 62, 61, 58, 57, 124, 123, 127, 128, 60, 132, 131]]  # <- probe list tool: e3
s5 = chamfer(s5, e3, 1)  # <- probe fillet tool: e3
e4 = [s5.edges()[i] for i in [22, 24, 25, 23, 21, 19, 17, 15, 14, 16, 18, 20]]  # <- probe list tool: e4
e4=homogenise(sample_curve(wire_from_edges(e4),100),0.5,1)
f1=fillet_by_offset(e4,s5,s5,1,1,auto_dir=1,d=1,closed_loop=1)
s6=difference(s5,swp_c(f1))
f2=mirror_surface(f1,[0,0,1],[0,0,5])
s7=difference(s6,swp_c(f2))
show(s7)
