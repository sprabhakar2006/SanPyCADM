
s1=linear_extrude(sec1,10)
s2=linear_extrude(sec2,25)
s3=[translate([0,0,-0.5], linear_extrude(p,27)) for p in sec3]
s4=difference(union([swp(s1), swp(s2)]), *[swp(p) for p in s3])
show(s4)