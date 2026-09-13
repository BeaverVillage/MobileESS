import os,sys,json,hashlib
from pathlib import Path
OUT=Path(__file__).absolute().parent
BASE=OUT.parent/'IEEE8500_scalability_20260910'
OVER=OUT.parent/'IEEE8500_pcc_overlay_20260911'
os.environ['MPLCONFIGDIR']=str(OUT/'plot_cache')
sys.path.insert(0,str(BASE/'selection_v2/plot_packages'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib import font_manager,patheffects
import numpy as np
files=[BASE/'audit/buses.json',BASE/'audit/topology_edges.json',BASE/'audit/primary_corridors.json',OVER/'FINAL_IMMUTABLE_TOPOLOGY_AUTHORITY.json',OVER/'PCC_OVERLAY_INVENTORY.json']
shas={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
buses={r['bus']:r for r in read(files[0])};edges=read(files[1]);primary=read(files[2]);sites=read(files[3])['locations'];pcc=read(files[4])
assert len(sites)==24 and len({r['ieee8500_bus'] for r in sites})==24
for r in sites:
    b=buses[r['ieee8500_bus']]
    assert (b['x'],b['y'])==(r['bus_x'],r['bus_y'])
    matches=[x for x in pcc if x['location_id']==r['location_id']]
    assert all(x['host_bus']==r['ieee8500_bus'] for x in matches)
    assert len(matches)==(2 if r['location_role']=='AIDC' else 1)
font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
plt.rcParams.update({'font.family':'Malgun Gothic','font.size':10,'axes.unicode_minus':False,'svg.fonttype':'none','pdf.fonttype':42})
blue='#1769aa';orange='#d36a20';ink='#1d3545';gray='#b5c2cb'
fig=plt.figure(figsize=(19,12.5),facecolor='white')
ax=fig.add_axes([.035,.115,.67,.755]);info=fig.add_axes([.735,.125,.245,.735]);info.set_axis_off()
fig.text(.04,.956,'IEEE8500 전력망 · 데이터센터와 충전소 위치',size=25,weight='bold',color=ink)
fig.text(.041,.922,'동결된 24개 electrical host  |  데이터센터 AIDC01–AIDC12 + 충전소 STA01–STA12',size=12,color='#617787')
origin=np.array([min(r['x'] for r in buses.values()),min(r['y'] for r in buses.values())])
xy=lambda name:np.array([buses[name]['x'],buses[name]['y']])-origin
valid=[e for e in edges if e['u'] in buses and e['v'] in buses and buses[e['u']]['coord_defined'] and buses[e['v']]['coord_defined']]
assert len(valid)==len(edges)
ax.add_collection(LineCollection([[xy(e['u']),xy(e['v'])] for e in valid],colors=gray,linewidths=.55,alpha=.72,zorder=1))
ax.add_collection(LineCollection([[xy(e['u']),xy(e['v'])] for e in primary],colors='#788e9d',linewidths=.9,alpha=.85,zorder=2))
for role,marker,color in [('AIDC','o',blue),('STA','D',orange)]:
    group=[r for r in sites if r['location_role']==role];coords=np.array([xy(r['ieee8500_bus']) for r in group])
    ax.scatter(*coords.T,s=90,marker=marker,c=color,edgecolors='white',linewidths=1.3,zorder=5)
root=xy('_hvmv_sub_lsb');ax.scatter(*root,marker='*',s=250,c=ink,edgecolors='white',linewidths=1,zorder=6)
ax.autoscale();ax.margins(x=.09,y=.08);ax.set_aspect('equal');ax.axis('off')
fig.canvas.draw();renderer=fig.canvas.get_renderer()
# Deterministic placement in display coordinates; labels move, electrical hosts do not.
boxes=[];marks=[ax.transData.transform(xy(r['ieee8500_bus'])) for r in sites]+[ax.transData.transform(root)]
offsets=[(12,12),(-12,12),(12,-15),(-12,-15),(15,25),(-15,25),(15,-28),(-15,-28),(38,4),(-38,4),(40,24),(-40,24),(40,-24),(-40,-24),(7,40),(-7,-40)]
labels=[(r['location_id'],xy(r['ieee8500_bus']),blue if r['location_role']=='AIDC' else orange) for r in sites]+[('변전소',root,ink)]
for name,pos,color in labels:
    trials=[]
    for dx,dy in offsets:
        ann=ax.annotate(name,pos,xytext=(dx,dy),textcoords='offset points',ha='left' if dx>0 else 'right',va='center',fontsize=10,fontweight='bold',color=color,bbox=dict(boxstyle='round,pad=.22',fc='white',ec=color,lw=.65,alpha=.97),arrowprops=dict(arrowstyle='-',color=color,lw=.75),zorder=7)
        fig.canvas.draw();bb=ann.get_bbox_patch().get_window_extent(renderer).expanded(1.06,1.15)
        penalty=sum(bb.overlaps(old) for old in boxes)*10000+sum(bb.contains(*m) for m in marks)*5000+abs(dx)+abs(dy)
        trials.append((penalty,dx,dy));ann.remove()
    _,dx,dy=min(trials)
    ann=ax.annotate(name,pos,xytext=(dx,dy),textcoords='offset points',ha='left' if dx>0 else 'right',va='center',fontsize=10,fontweight='bold',color=color,bbox=dict(boxstyle='round,pad=.22',fc='white',ec=color,lw=.65,alpha=.97),arrowprops=dict(arrowstyle='-',color=color,lw=.75),zorder=7)
    fig.canvas.draw();boxes.append(ann.get_bbox_patch().get_window_extent(renderer).expanded(1.06,1.15))
info.text(0,1.025,'표시 기준',size=14,weight='bold',color=ink)
info.scatter([.025],[.968],s=90,c=blue,marker='o',transform=info.transAxes)
info.text(.085,.968,'데이터센터 12곳',va='center',size=12,color=blue,transform=info.transAxes)
info.scatter([.025],[.922],s=80,c=orange,marker='D',transform=info.transAxes)
info.text(.085,.922,'충전소 12곳',va='center',size=12,color=orange,transform=info.transAxes)
info.text(0,.868,'모든 24곳에서 MESS 접속 가능',size=10.5,color='#617787',transform=info.transAxes)
info.plot([0,1],[.837,.837],color='#dce4e9',lw=1,transform=info.transAxes)
info.text(0,.801,'위치 ID',size=10,weight='bold',color=ink,transform=info.transAxes)
info.text(.34,.801,'IEEE8500 host bus',size=10,weight='bold',color=ink,transform=info.transAxes)
for i,r in enumerate(sites):
    yy=.765-i*.0288;color=blue if r['location_role']=='AIDC' else orange
    info.text(0,yy,r['location_id'],color=color,size=10,weight='bold',transform=info.transAxes)
    info.text(.34,yy,r['ieee8500_bus'],color=ink,size=10,transform=info.transAxes)
info.set_xlim(0,1);info.set_ylim(0,1)
fig.text(.041,.065,'회색: IEEE8500 배선   ·   진한 회색: 3상 primary 경로   ·   별: feeder 변전소',size=10.5,color='#526b7b')
fig.text(.041,.037,'원본 Buscoords의 상대 좌표를 사용했습니다. 좌표계·거리 단위는 미확정이며, PCC는 연결된 host 위치에 표시했습니다.',size=9.5,color='#6a7c88')
stem=OUT/'IEEE8500_AIDC_STA_LOCATIONS'
for ext in ('png','pdf','svg'):fig.savefig(str(stem)+'.'+ext,dpi=210,facecolor='white')
plt.close(fig)
assert shas=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
manifest=dict(status='PASS',source_files_unchanged=True,source_sha256=shas,AIDC_count=12,STA_count=12,native_bus_count=len(buses),native_topology_edges=len(valid),figure_is_coordinate_topology_not_performance=True,locations=sites,artifacts=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [Path(str(stem)+'.'+x) for x in ('png','pdf','svg')]])
(OUT/'FIGURE_PROVENANCE.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print('FIGURE_PASS',str(stem)+'.png',flush=True)
