s1=swp(linear_extrude(sec1,10))
s2=[ swp(linear_extrude(p,10)) for p in sec2]
s3=difference(s1,*s2)
pl1=plane_from_equation([-1,0,0,132-58/2-15])
s4=swp(surface_line_vector(sec3_3d,[10,0,0]))
s5=[ swp(surface_line_vector(p,[10,0,0])) for p in sec4_3d]
s6=difference(s4,*s5)
pl2=plane_from_equation([0,-1,0,0])
s7=swp(sweep_sec2path(sec5,path1_3d))
s8=swp(sweep_sec2path(sec6,path1_3d))
s9=union([s3,s6,s7])
s10=difference(s9,s8)
show(s10)