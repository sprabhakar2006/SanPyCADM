
s1=swp(linear_extrude(sec1,10))
s2=swp(translate([0,0,2],linear_extrude(sec2,8)))
s3=difference(s1,s2)
s4=[swp(translate([0,0,-0.5],linear_extrude(p,11))) for p in sec3]
s5=difference(s3,*s4)
e1 = [s5.edges()[i] for i in [83, 87, 89, 85, 81, 77, 73, 69, 66, 71, 75, 79]]  # <- probe list tool: e1
s5 = fillet(s5, e1, 1)  # <- probe fillet tool: e1
e2 = [s5.edges()[i] for i in [32, 34, 35, 33, 31, 29, 27, 26, 2, 6, 28, 30]]  # <- probe list tool: e2
s5 = fillet(s5, e2, 1)  # <- probe fillet tool: e2
e3 = [s5.edges()[i] for i in [51, 50, 49, 48, 47, 46, 119, 118, 111, 110, 115, 114]]  # <- probe list tool: e3
s5 = chamfer(s5, e3, 1)  # <- probe fillet tool: e3
e4 = [s5.edges()[i] for i in [20, 18, 16, 14, 15, 17, 19, 21, 23, 25, 24, 22]]  # <- probe list tool: e4
s5 = fillet(s5, e4, 1)  # <- probe fillet tool: e4
e5 = [s5.edges()[i] for i in [96, 91, 93, 97, 101, 105, 109, 113, 112, 108, 104, 100]]  # <- probe list tool: e5
s5 = fillet(s5, e5, 1)  # <- probe fillet tool: e5
show(s5)