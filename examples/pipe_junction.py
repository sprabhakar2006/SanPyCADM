
pl1=swp_surf(plane_from_equation([0,-1,0,40]))
s1=swp(surface_line_vector(sec1_3d[0],[0,80,0]))
s2=swp(surface_line_vector(sec1_3d[1],[0,80,0]))
s3=difference(s2,s1)
s4=[swp(surface_line_vector(p,[0,10,0])) for p in sec2_3d]
s5=[swp(surface_line_vector(p,[0,10,0])) for p in sec3_3d]
s6=union([s2,*s4])
s6=difference(s6,*s5)
pl2=swp_surf(plane_from_equation([0,0,1,80]))
s7=swp(surface_line_vector(sec4_3d,[0,0,-10]))
s8=[swp(surface_line_vector(p,[0,0,-11])) for p in sec5_3d]
s9=difference(s7,*s8)
pl3=swp_surf(plane_from_equation([-1,0,0,100]))
s10=swp(surface_line_vector(sec6_3d[0],[20,0,0]))
s11=swp(surface_line_vector(sec6_3d[1],[85,0,0]))
s12=union([s10,s11])
s13=translate([-1,0,0],swp(surface_line_vector(sec6_3d[2],[87,0,0])))
s14=difference(s12,s13)
pl4=swp_surf(plane_from_equation([0,-1,0,0]))
p1=path1_3d[3:]
s15=swp(sweep_sec2path(circle(25),p1))
f1 =translate([0,0,-1],s9.faces()[1])
s15=split(s15,f1,'bottom')
s16=union([s9,s15])
s17=swp(sweep_sec2path(circle(20),path1_3d[1:]))
s18=difference(s16,s17)
c1=swp(surface_line_vector(sec7_3d,[0,80,0]))
# s14=difference(s14,c1)
# s18=difference(s18,c1)
pl5=swp_surf(plane_from_equation([0,0,1,-100]))
s19=swp(linear_extrude(sec8_3d[0],10))
s20=swp(linear_extrude(sec8_3d[1],80))
s21=union([s19,s20])
c2=swp(linear_extrude(sec8_3d[2],80))
c3=[swp(linear_extrude(p,10)) for p in sec8_3d[3:]]
s21=difference(s21,*c3)
# s21=difference(s21,c1)
s22=union([s6,s12,s16,s21])
s23=difference(s22,s17,s13,c2,s1)
# show(s6,s14,s18, pl5,s21)
e1 = [s23.edges()[i] for i in [62, 97, 11, 42, 43, 41, 45, 5, 6, 7, 55, 57, 52, 53, 101, 100]]  # <- probe list tool: e1
s23 = fillet_variable(s23, e1, 5)  # <- probe variable fillet: e1
e2 = [s23.edges()[i] for i in [132, 131, 136, 135]]  # <- probe list tool: e2
s23 = chamfer(s23, e2, 2)  # <- probe fillet tool: e2
e3 = [s23.edges()[i] for i in [80, 83, 75, 71, 69, 65]]  # <- probe list tool: e3
s23 = fillet(s23, e3, 5)  # <- probe fillet tool: e3
show(s23)



