
p1=sec1
s1=prism(circle(10),p1)
pl1=translate([0,0,40],plane_from_equation([1,0,0,0]))
s2=surface_offset(s1,1)
s3=surface_line_vector(sec2_3d,[20,0,0])
s4=difference(swp(s3),swp(s2))
s5=[ swp(rot(f'z{i}',s4))  for i in [0,120,240]]
s6=difference(swp(s1),*s5)
e1 = [s6.edges()[i] for i in [36, 35, 33, 31, 29, 2, 4, 6, 8, 10, 12, 11, 9, 30, 32, 34]]  # <- probe list tool: e1
s6 = fillet(s6, e1, 0.4)  # <- probe fillet tool: e1
e2 = [s6.edges()[i] for i in [173, 172, 170, 168, 166, 164, 144, 145, 147, 149, 151, 153, 159, 161, 156, 157]]  # <- probe list tool: e2
s6 = fillet_variable(s6, e2, 0.5)  # <- probe variable fillet: e2
e3 = [s6.edges()[i] for i in [35, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34]]  # <- probe list tool: e3
s6 = fillet(s6, e3, 0.4)  # <- probe fillet tool: e3
e4 = [s6.edges()[i] for i in [78, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77]]  # <- probe list tool: e4
s6 = fillet(s6, e4, 0.4)  # <- probe fillet tool: e4
e5 = [s6.edges()[i] for i in [105, 99, 101, 106, 110, 114, 118, 122, 124, 127, 126, 121, 117, 113, 109, 104]]  # <- probe list tool: e5
s6 = fillet_variable(s6, e5, 0.5)  # <- probe variable fillet: e5
e6 = [s6.edges()[i] for i in [217, 211, 213, 218, 222, 226, 230, 234, 236, 239, 238, 233, 229, 225, 221, 216]]  # <- probe list tool: e6
s6 = fillet_variable(s6, e6, 0.5)  # <- probe variable fillet: e6
f1=s6.faces()
f1=shell_from_faces( [f1[i] for i in range(len(f1)) if i!=24])
s7=thicken_shell(f1,-1)
show(s7)