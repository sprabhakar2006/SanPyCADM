s1=linear_extrude(clean_profile( sec1), 20)
s2=[translate([0,0,-0.5], linear_extrude(p,22)) for p in sec2]
s3=difference(swp(s1), *[swp(p) for p in s2])
show(s3)
