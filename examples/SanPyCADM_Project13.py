n=20 # number of strands in the lamp
t=5 # thickness of each strand
path=[[42,0],[62,50],[25,100],[25,180]]
path1=cytz(bezier(path,100))
path2=[rot(f'z{180/100*i:3f}',path1[i]) for i in range(len(path1))]
sec_list=[translate(path2[i],rot(f'z{180/100*i:3f}',offset(square(t,center=1),-1.5/100*i))) for i in range(len(path1))]
s1=[swp(rot(f'z{i}',sec_list)) for i in linspace(0,360,n+1)[:-1]]
s2=[mirror_surface(p,[0,1,0],[0,0,0]) for p in s1]
c1=swp(linear_extrude(circle(45),3))
c2=swp(linear_extrude(circle(30),3))
s3=translate([0,0,-0.1],difference(c1,c2))
show(*s1,*s2,s3)

