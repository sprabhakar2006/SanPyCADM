
s1=swp(linear_extrude(sec1,10))
s2=swp(translate([0,0,2],linear_extrude(sec2,8)))
s3=difference(s1,s2)
s4=[swp(translate([0,0,-0.5],linear_extrude(p,11))) for p in sec3]
s5=difference(s3,*s4)
e1 = [s5.edges()[i] for i in [27, 25, 22, 2, 23, 24, 26, 28, 30, 32, 31]]  # <- probe list tool: e1
s5 = fillet(s5, e1, 1)  # <- probe fillet tool: e1
e2 = [s5.edges()[i] for i in [52, 50, 48, 47, 49, 51, 53, 55, 57, 58, 56]]  # <- probe list tool: e2
s5 = fillet(s5, e2, 1)  # <- probe fillet tool: e2
e3 = [s5.edges()[i] for i in [24, 25, 28, 29, 27, 26, 81, 80, 85, 84, 89, 88]]  # <- probe list tool: e3
s5 = chamfer(s5, e3, 1)  # <- probe fillet tool: e3
e4 = [s5.edges()[i] for i in [128, 124, 119, 121, 125, 129, 133, 137, 141, 140, 136]]  # <- probe list tool: e4
s5 = fillet(s5, e4, 1)  # <- probe fillet tool: e4
e6 = [s5.edges()[i] for i in [177, 173, 169, 165, 163, 168, 172, 176, 180, 184, 185]]  # <- probe list tool: e6
s5 = fillet(s5, e6, 1)  # <- probe fillet tool: e6
show(s5)