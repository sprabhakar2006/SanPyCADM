s1=rot('y90',homogenise(cr2dt([[-35,-35,10],[70,0,10],[0,70,10],[-70,0,10]]),.5,1))
l1=70
l2=l_lenv_o(s1)-.01
n1=3
n2=int(n1/l1*l2)
w1=rot('x90',sinewave(l1,n1,1,100))
w2=rot('x90z90',sinewave(l2,n2,1,int(100/l1*l2)))
s2=surface_from_2_waves(w1,w2)
s3=rot('y-90',wrap_surface_around_path(s2,s1))
s4=[offset_3d(p,-2) for p in s3]
pl1=plane_from_equation([0,0,1,2])
e1=equidistant_pathc( contiguous_chains( surface_solid_open_intersection(pl1,s4))[0],200)
f1=fillet_by_offset(e1,s4,pl1,6,-6,closed_loop=1,auto_dir=0)
s5=split(swp(s4),swp_surf(pl1),'top')
s6=difference(swp(s3),s5)
e2 = [s6.edges()[i] for i in [2, 5, 7, 6]]  # <- probe list tool: e2
s6 = fillet(s6, e2, 0.8)  # <- probe fillet tool: e2
e3 = [s6.edges()[i] for i in [5, 2]]  # <- probe list tool: e3
s6 = fillet(s6, e3, 2)  # <- probe fillet tool: e3
show(s6, swp_c(f1))
