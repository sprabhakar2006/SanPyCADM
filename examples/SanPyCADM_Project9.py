
s1=sweep_sec2path(sec1,rot('x90', path1))
s2=sweep_sec2path(sec2, rot('x90', path2))
s3=swp(solid_from_2surfaces(s1,s2))
c1=swp(linear_extrude(circle(55/2),20))
e1 = [c1.edges()[i] for i in [5, 2, 0, 4]]  # <- probe list tool: e1
c1 = fillet(c1, e1, 1)  # <- probe fillet tool: e1
c2=translate([-50,0,50],rot('y90',c1))
s4=sweep_sec2path(sec3,rot('x90', path3))
s5=sweep_sec2path(sec4, rot('x90', path4))
s6=swp(solid_from_2surfaces(s5,s4))
s7=swp(linear_extrude(sec5_3d,-20))
# show(s3, c1, c2, s6)
f1 = [s7.faces()[i] for i in [12, 11, 10, 9, 8, 7, 6, 5, 4]]  # <- probe list tool: f1
f1=shell_from_faces(f1)
s6=split(s6,f1,'bottom')
s8=swp(linear_extrude(sec6_3d,-20))
# s9=union([s3,s6,s7,s8,c1,c2])
s9=union([s7,s8])
e2 = [s9.edges()[i] for i in [51, 2]]  # <- probe list tool: e2
s9 = fillet(s9, e2, 1)  # <- probe fillet tool: e2
e3 = [s9.edges()[i] for i in [33, 35, 37, 39, 41, 43, 45, 44, 42, 12, 13, 15, 17, 19, 21, 23, 22, 20]]  # <- probe list tool: e3
s9 = fillet(s9, e3, 1)  # <- probe fillet tool: e3
e4 = [s9.edges()[i] for i in [66, 60, 57, 53, 49, 45, 40, 37, 32, 28, 20, 18, 16, 14, 12, 10, 8, 6, 4, 2]]  # <- probe list tool: e4
s9 = translate([-.01,0,0.01],fillet(s9, e4, 1))  # <- probe fillet tool: e4)
s10=union([s3,s6,c1,c2,s9])
c3=swp(translate([0,0,-0.5],linear_extrude(circle(45/2),21)))
c4=translate([-50.5,0,50],rot('y90',c3))
s11=difference(s10,c3,c4)
s12=swp(translate([-55,0,-10],o_solid([0,1,0],square(60),2,-1)))
s13=difference(s11,s12)
s14=swp(translate([0,0,.5],linear_extrude(sec7_3d,-21)))
s15=difference(s13,s14)
show(s15)




