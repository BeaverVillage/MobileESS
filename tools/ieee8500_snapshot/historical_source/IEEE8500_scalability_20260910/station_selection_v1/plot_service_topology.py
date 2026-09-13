import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
sys.dont_write_bytecode=True
os.environ['MPLCONFIGDIR']=str(ROOT/'plot_cache')
sys.path.insert(0,str(BASE/'selection_v2/plot_packages'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
reg=read(ROOT/'FINAL_24_LOCATION_ELECTRICAL_MAPPING.json');buses={b['bus']:b for b in read(BASE/'audit/buses.json')};edges=read(BASE/'audit/primary_corridors.json')
paths=read(ROOT/'SERVICE_ROOT_PATHS.json')
xy=lambda b:(buses[b]['x'],buses[b]['y'])
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','font.size':10})
fig=plt.figure(figsize=(19,12));ax=fig.add_axes([.045,.10,.61,.80]);info=fig.add_axes([.70,.10,.29,.80]);info.axis('off')
ax.add_collection(LineCollection([[xy(e['u']),xy(e['v'])] for e in edges],colors='#cbd2d7',linewidths=.8,zorder=1))
pathpairs=set()
for r in paths:pathpairs.update(tuple(sorted([a,b])) for a,b in zip(r['root_to_host_path'][:-1],r['root_to_host_path'][1:]))
ax.add_collection(LineCollection([[xy(a),xy(b)] for a,b in sorted(pathpairs)],colors='#7e9697',linewidths=1.3,zorder=2))
acol='#206493';scol='#bc5a19'
offsets={'AIDC01':(13,7),'AIDC02':(-42,-16),'AIDC03':(-40,-12),'AIDC04':(12,13),'AIDC05':(-42,-12),'AIDC06':(13,-20),'AIDC07':(-45,-8),'AIDC08':(12,-20),'AIDC09':(12,15),'AIDC10':(12,-23),'AIDC11':(-38,-18),'AIDC12':(12,14),'STA01':(-40,13),'STA02':(12,16),'STA03':(12,-18),'STA04':(12,-19),'STA05':(-38,15),'STA06':(-42,-18),'STA07':(-38,13),'STA08':(12,14),'STA09':(12,-18),'STA10':(-40,10),'STA11':(12,12),'STA12':(12,15)}
for r in reg:
    name=r['location_id'];aidc=r['location_role']=='AIDC';col=acol if aidc else scol;label=('A' if aidc else 'S')+name[-2:];x,y=r['bus_x'],r['bus_y']
    ax.scatter([x],[y],marker='o' if aidc else 'D',c=col,s=55,edgecolors='white',linewidths=.7,zorder=4)
    ax.annotate(label,(x,y),xytext=offsets[name],textcoords='offset points',color=col,fontweight='bold',fontsize=9,bbox={'boxstyle':'round,pad=0.15','fc':'white','ec':col,'lw':.6},arrowprops={'arrowstyle':'-','color':col,'lw':.7},zorder=5)
rx,ry=xy('_hvmv_sub_lsb');ax.scatter([rx],[ry],s=160,marker='*',c='#172d3c',edgecolors='white',zorder=5);ax.annotate('ROOT',(rx,ry),xytext=(10,18),textcoords='offset points',fontweight='bold',fontsize=9,arrowprops={'arrowstyle':'-','color':'#172d3c'})
ax.autoscale();ax.margins(.08);ax.set_aspect('equal');ax.grid(alpha=.13);ax.set_xlabel('Canonical Buscoords X (original units)');ax.set_ylabel('Canonical Buscoords Y (original units)');ax.ticklabel_format(style='plain',useOffset=False)
info.text(0,1,'24 MESS service locations',fontsize=16,fontweight='bold',va='top');info.text(0,.952,'ID        IEEE8500 host                 Root ohm',fontsize=10,color='#52616b',va='top')
for i,r in enumerate(reg):
    y=.916-i*.030;col=acol if r['location_role']=='AIDC' else scol
    info.text(0,y,r['location_id'],fontsize=9.5,color=col,fontweight='bold',va='top');info.text(.22,y,r['ieee8500_bus'],fontsize=9.5,va='top');info.text(.81,y,f"{r['electrical_root_distance_ohm']:.3f}",fontsize=9.5,va='top')
info.text(0,.13,'● A01–A12: FINAL AIDC hosts',color=acol,fontsize=11);info.text(0,.09,'◆ S01–S12: selected station hosts',color=scol,fontsize=11);info.text(0,.035,'All 24 locations support MESS service.\nNearby AIDC–STA hosts remain visible.',fontsize=10,color='#52616b',linespacing=1.5)
fig.text(.045,.96,'IEEE8500 | Fixed AIDC + selected MESS stations',fontsize=23,fontweight='bold',color='#172d3c');fig.text(.045,.924,'12 immutable AIDC hosts + 12 distinct STA hosts  •  647 ABC-primary buses / 646 corridors',fontsize=12,color='#52616b')
fig.text(.045,.035,'Topology-only registry. No PCC transformers, background scaling or B0–B3 runs. Coordinate CRS/native units are not established.',fontsize=10,color='#52616b')
fig.savefig(ROOT/'FINAL_24_LOCATION_TOPOLOGY.png',dpi=180);fig.savefig(ROOT/'FINAL_24_LOCATION_TOPOLOGY.svg');plt.close(fig)
a=read(ROOT/'STA_GEOMETRY_ALIGNMENT.json');v=read(ROOT/'REGISTRY_VALIDATION.json')['STA_metrics'];x=np.array(a['melbourne_aligned']);y=np.array(a['selected_normalized'])
fig,ax=plt.subplots(figsize=(10,8));ax.scatter(x[:,0],x[:,1],s=85,facecolors='none',edgecolors=acol,label='STA Melbourne anchors (proper rotation)');ax.scatter(y[:,0],y[:,1],marker='D',s=50,c=scol,label='STA electrical hosts')
for i,(p,q) in enumerate(zip(x,y),1):ax.plot([p[0],q[0]],[p[1],q[1]],lw=.7,c='#a5b0b6');ax.annotate(f'S{i:02}',q,xytext=(6,6),textcoords='offset points',fontsize=9)
ax.grid(alpha=.15);ax.set_aspect('equal');ax.set_xlabel('Centered / RMS-normalized X');ax.set_ylabel('Centered / RMS-normalized Y');ax.legend(loc='best');ax.set_title(f"STA relative geometry | E_coord={v['E_coord']:.6f}, E_pair={v['E_pair']:.6f}\nTwo-neighbor retention {v['nearest_neighbor_retention']:.2%}",pad=15);fig.tight_layout();fig.savefig(ROOT/'STA_GEOMETRY_DIAGNOSTIC.png',dpi=160);plt.close(fig)
print('Saved 24-location topology PNG/SVG and STA geometry diagnostic.')
