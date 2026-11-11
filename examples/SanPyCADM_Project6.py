s1=sphere(90)
s2=sphere(80)
s3=linear_extrude(sec1,10)
s4=linear_extrude(sec2,120)
s5=linear_extrude(sec3,120)
s6=[translate([0,0,-0.5],linear_extrude(p,11)) for p in sec4]
s7=union(swp(s3),swp(s5))
s7=difference(s7,swp(s4),*[swp(p) for p in s6])
s8=linear_extrude(sec5,10)
s9=linear_extrude(sec6,120)
s10=linear_extrude(sec7,120)
s11=[translate([0,0,-0.5],linear_extrude(p,11)) for p in sec8]
s12=difference(union([swp(s8),swp(s10)]),swp(s9),*[swp(p) for p in s11])
s13=translate([-135,0,0],rot('y90',s7))
s14=translate([135,0,0],rot('y-90',s7))
s15=translate([0,0,135],rot('y180',s12))
s16=difference(union([s13,s14,s15]),sphere(80))
s17=difference(swp(s1),swp(s2))
c1=o_solid([1,0,0],circle(42),500,-250)
c2=o_solid([0,0,1],circle(42),500)
s17=difference(s17,swp(c1),swp(c2))
s18=union([s16,s17])
e1 = [s18.edges()[i] for i in [68, 61]]  # <- probe list tool: e1
f_e1 = translate([0,0,.01],fillet_by_offset(e1, s18, s18, 5, -5, auto_dir=0, as_solid=1))  # <- probe offset fillet tool: e1
f_e1a=rot('y90',f_e1)
f_e1b=rot('y-90',f_e1)
s18 = union([s18, swp(f_e1),swp(f_e1a),swp(f_e1b)])  # <- probe offset fillet union: e1
e2 = [s18.edges()[i] for i in [241, 242, 240]]  # <- probe list tool: e2
f_e2 = translate([0,0,-0.02],fillet_by_offset(e2, s18, s18, 5, -5, auto_dir=0, as_solid=1))  # <- probe offset fillet tool: e2
f_e2a=rot('y90',f_e2)
f_e2b=rot('y-90',f_e2)
s18 = union([s18, swp(f_e2),swp(f_e2a),swp(f_e2b)])  # <- probe offset fillet union: e2
e3 = [s18.edges()[i] for i in [129, 111, 4]]  # <- probe list tool: e3
s18 = chamfer(s18, e3, 2)  # <- probe fillet tool: e3
e4 = [s18.edges()[i] for i in [39, 113, 109]]  # <- probe list tool: e4
s18 = chamfer(s18, e4, 5)  # <- probe fillet tool: e4
show(s18)