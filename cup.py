s1=circle(20)
s2=sec1
s3=prism(s1,s2)
pl1=plane_from_equation([-1,0,0,0])
s4=split(swp(s3),swp_surf(pl1),'top')
p2=homogenise(path2_3d,0.5)
sk1=sec3
s5=sweep_sec2path(sk1,p2)
s6=prism(s1,s2[46:])
s5=difference(swp(s5),swp(s6))
cup=union([swp(s3),s5])
e1 = [cup.edges()[i] for i in [5, 2, 23, 25]]  # <- probe list tool: e1
cup = fillet(cup, e1, 1)  # <- probe fillet tool: e1
e2 = [cup.edges()[i] for i in [8]]  # <- probe list tool: e2
cup = fillet(cup, e2, 1.5)  # <- probe fillet tool: e2
e3 = [cup.edges()[i] for i in [18]]  # <- probe list tool: e3
cup = fillet(cup, e3, 2)  # <- probe fillet tool: e3
show(cup)
