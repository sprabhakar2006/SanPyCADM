s1=solid_line_vector(c1,[0,0,50])
s2=solid_line_vector(c2,[0,0,50])
r1=difference(s1,s2)
pl1=plane_from_equation([1,0,0,0],[100,100])
l1=sec1_3d
s3=solid_line_vector(l1,[50,0,0])
r1=difference(r1,s3)

e1 = [r1.edges()[i] for i in [24, 25, 26, 27, 1, 2, 3, 4, 5, 44, 46, 48, 50, 53, 52, 59, 61, 63, 65, 67, 69, 71, 73, 74, 32, 31, 34, 36, 38, 40, 42, 7, 8, 9, 10, 11, 17, 18, 19, 20, 21, 22, 23, 6]]  # <- probe list tool: e1
r1 = fillet(r1, e1, 0.75)  # <- probe fillet tool: e1
e2 = [r1.edges()[i] for i in [17, 6, 38, 39, 32, 2, 33]]  # <- probe list tool: e2
r1 = fillet(r1, e2, 0.75)  # <- probe fillet tool: e2
show(r1)
