s1=prism(c1,path)
p1=helix(7.5,2.01,20,5)
s2=sweep_sec2path(sec1,p1,orientation=3)
# You choose per shape: swp(x) = exact B-rep, as_mesh(x) = fast mesh (same as SanPyCAD).
# difference() uses the fast mesh boolean as soon as one operand is a mesh.
r1=difference(as_mesh(s1),as_mesh(s2))
# show(color(s1, alpha=0.2))
# show(color(s2, [1, 0, 0], alpha=0.8))
show(r1)
