"""Static source diagrams only; never synthesize missing AC measurements."""
import csv
import json
import os
from pathlib import Path

from .audit import DOC, read, save
os.environ['MPLCONFIGDIR']=str(Path(read(DOC/'RUNTIME_ENVIRONMENT.json')['runtime'])/'matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

def main():
    axes=read(DOC/'OFFICIAL_BALANCED_AXES.json')
    rows=list(csv.DictReader((DOC/'AIDC12_STA12_PCC_MAPPING.csv').open(encoding='utf-8')))
    coords={k:(v['x'],v['y']) for k,v in axes['buses'].items() if v['x'] or v['y']}
    original_coord_count=len(coords)
    # Fill only missing positions along the actual connection graph for drawing.
    # Coordinates are not new electrical/GIS inputs and do not change the model.
    links=[]
    for r in axes['lines']+axes['transformers']:
        buses=[b.split('.')[0].lower() for b in r['buses']]
        links.extend((buses[0],b) for b in buses[1:])
    for _ in range(len(axes['buses'])):
        changed=False
        for a,b in links:
            if a in coords and b not in coords:
                coords[b]=coords[a];changed=True
            elif b in coords and a not in coords:
                coords[a]=coords[b];changed=True
        if not changed:
            break
    output=DOC/'figures';output.mkdir(exist_ok=True)
    segments={'MV':[],'LV':[]};missing=[]
    for r in axes['lines']:
        a,b=[v.split('.')[0].lower() for v in r['buses']]
        if a not in coords or b not in coords:
            missing.append(r['name']);continue
        segments['LV' if r['triplex'] or r['kv_ln']<1 else 'MV'].append([coords[a],coords[b]])
    fig,ax=plt.subplots(figsize=(10,10),layout='constrained')
    for kind,color,width in [('LV','#b9c4d1',.45),('MV','#385d80',.8)]:
        ax.add_collection(LineCollection(segments[kind],colors=color,linewidths=width,label=f'{kind}: {len(segments[kind])} original lines'))
    ax.autoscale();ax.set_aspect('equal');ax.set_axis_off()
    ax.set_title('V2_add | Official IEEE8500 Balanced\nOriginal topology; source inventory only',fontsize=15)
    ax.legend(loc='lower left',frameon=False)
    fig.savefig(output/'IEEE8500_BALANCED_TOPOLOGY.svg');fig.savefig(output/'IEEE8500_BALANCED_TOPOLOGY.png',dpi=160)
    for role,marker,color in [('AIDC','o','#c85a36'),('STA','s','#16857b')]:
        chosen=[r for r in rows if r['role']==role]
        x,y=zip(*(coords[r['candidate_bus'].lower()] for r in chosen))
        ax.scatter(x,y,s=45,marker=marker,color=color,edgecolor='white',linewidth=.6,zorder=5,label=role+'12 C2 candidate')
        for r in chosen:
            x,y=coords[r['candidate_bus'].lower()]
            offsets={'STA01':(-38,-4),'STA02':(5,8),'STA03':(5,8),'AIDC10':(4,-13),
                     'STA04':(-40,1),'AIDC05':(5,-11),'STA05':(-38,5),'AIDC06':(-43,-9),
                     'STA06':(5,8),'AIDC07':(5,-13),'STA07':(-38,-5),
                     'STA10':(5,-10),'STA11':(5,8)}
            ax.annotate(r['location_id'],(x,y),xytext=offsets.get(r['location_id'],(4,4)),
                        textcoords='offset points',fontsize=7,color=color,
                        bbox=dict(facecolor='white',edgecolor='none',alpha=.75,pad=.3))
    ax.set_title('V2_add | AIDC12 + STA12\nPR199 C2 candidates: V44 hardware acceptance NOT_VERIFIED',fontsize=13)
    ax.legend(loc='lower left',frameon=False)
    fig.savefig(output/'AIDC12_STA12_C2_CANDIDATES.svg');fig.savefig(output/'AIDC12_STA12_C2_CANDIDATES.png',dpi=160)
    plt.close(fig)
    save('FIGURE_READINESS.json',dict(
        topology=dict(status='GENERATED_SOURCE_ONLY',line_segments_drawn=sum(map(len,segments.values())),
                      original_line_count=len(axes['lines']),missing_lines=missing,
                      original_coordinate_count=original_coord_count,
                      graph_propagated_missing_coordinate_count=len(coords)-original_coord_count,
                      coordinates='official drawing coordinates; inferred points only for missing drawing positions; no field GIS claim'),
        PCC_positions='GENERATED_C2_CANDIDATES_NOT_HARDWARE_CERTIFIED',
        loading_heatmap='NOT_VERIFIED_NO_B0',scale_MV_LV='NOT_VERIFIED_NO_B0',
        global_sensitivity='NOT_VERIFIED_NO_PILOT',critical_lines_PCC='NOT_VERIFIED_NO_B0',
        arms_timeseries='NOT_VERIFIED_NO_OPTIMIZATION',arms_daily_mean_and_max='NOT_VERIFIED_NO_OPTIMIZATION',
        image_generation_AI_used=False))


if __name__=='__main__':main()
