
p1= rot('y90',homogenise( cr2dt([[-35,-35,7],[70,0,7],[0,70,7],[-70,0,7]]), 1, 1))
l1=rot('x90',sinewave(70,3,1,100))
d1=l_lenv_o(p1)-.01
n1=int(3/70*d1)
l2=rot('x90z90',sinewave(d1,n1,1,100))
s1=surface_from_2_waves(l1,l2)
s2=rot('y-90',wrap_surface_around_path(s1,p1))
s3=swp([ offset_3d(p,-1) for p in s2])
s2=swp(s2)
pl1=swp_surf(plane_from_equation([0,0,1,2],[200,200]))
s4=split(s3,pl1,'top')
s5=difference(s2,s4)
e1 = [s5.edges()[i] for i in [0, 4]]  # <- probe list tool: e1
s5 = fillet(s5, e1, 2)  # <- probe fillet tool: e1
e2 = [s5.edges()[i] for i in [2, 5, 10, 9]]  # <- probe list tool: e2
s5 = fillet(s5, e2, 0.45)  # <- probe fillet tool: e2
e3 = [s5.edges()[i] for i in [21, 23]]  # <- probe list tool: e3
s5 = fillet(s5, e3, 4)  # <- probe fillet tool: e3
show(s5)