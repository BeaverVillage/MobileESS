"""Static original topology and frozen-input figures only; no AC claims."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from ac import DOC,save


def main():
    folder=DOC/'figures';folder.mkdir(exist_ok=True)
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text());buses={r['bus']:r for r in inv['bus_rows']};groups={}
    for row in inv['line_rows']:
        a,b=[row[k].split('.')[0] for k in ('bus1','bus2')]
        if a in buses and b in buses and buses[a]['coords'] and buses[b]['coords']:
            groups.setdefault(row['feeder'],[]).append([(buses[a]['x'],buses[a]['y']),(buses[b]['x'],buses[b]['y'])])
    fig,ax=plt.subplots(figsize=(10,8))
    for i,(name,lines) in enumerate(groups.items()):
        ax.add_collection(LineCollection(lines,linewidths=.4,colors=['#777777','#0072B2','#D55E00','#009E73'][i%4],label=name))
    ax.autoscale();ax.set_aspect('equal');ax.legend(fontsize=8);ax.set_xlabel('Original GIS x');ax.set_ylabel('Original GIS y')
    ax.set_title('V1_add: original SMART-DS uhs2_1247 topology\n6572 buses / 12749 electrical nodes; loading not measured')
    fig.tight_layout();fig.savefig(folder/'ORIGINAL_SUBSTATION_TOPOLOGY.svg',metadata={'Date':None});plt.close(fig)
    z=np.load(DOC/'IEEE123_FROZEN_ELECTRICAL_INPUTS.npz');fig,axes=plt.subplots(2,2,figsize=(11,6),sharex=True)
    for ax,q in zip(axes.ravel(),['BG_P_kw','BG_Q_kvar','PV_P_kw','AIDC_P_kw']):
        for role,sl in [('PLANNING',slice(None)),('ACTUAL',slice(24,None))]:
            ax.plot(np.arange(96)/4,z[role+'_'+q][sl].sum(1),label=role)
        ax.set_title(q);ax.grid(alpha=.2)
    axes[0,0].legend();axes[1,0].set_xlabel('Evaluation hour AEST');axes[1,1].set_xlabel('Evaluation hour AEST')
    fig.suptitle('V1_add source audit: frozen IEEE123 inputs, no Greensboro AC')
    fig.tight_layout();fig.savefig(folder/'FROZEN_IEEE123_INPUT_TOTALS.svg',metadata={'Date':None});plt.close(fig)
    import csv
    with(DOC/'AIDC12_PCC_CANDIDATES.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    unique={r['bus']:r for r in rows};feeders=[k for k in groups if k!='substation_shared']
    fig,axes=plt.subplots(1,3,figsize=(15,6))
    for ax,name in zip(axes,feeders):
        ax.add_collection(LineCollection(groups[name],linewidths=.4,colors='#aaaaaa'))
        rr=[r for r in unique.values() if r['feeder']==name]
        ax.scatter([float(r['x'])for r in rr],[float(r['y'])for r in rr],s=12,c='#0072B2')
        ax.autoscale();ax.set_aspect('equal');ax.set_title(name+'\n'+str(len(rr))+' LV candidates',fontsize=9)
        ax.tick_params(labelsize=7)
    fig.suptitle('V1_add: transformer/voltage candidates only — AIDC12/STA12 assignment NOT VERIFIED')
    fig.tight_layout();fig.savefig(folder/'STATIC_PCC_CANDIDATES.svg',metadata={'Date':None});plt.close(fig)
    save('FIGURE_STATUS.json',dict(experiment='V1_add',generated=['ORIGINAL_SUBSTATION_TOPOLOGY.svg',
        'FROZEN_IEEE123_INPUT_TOTALS.svg','STATIC_PCC_CANDIDATES.svg'],
        not_generated={name:'INPUT_MAPPING_NOT_VERIFIED; no invented measurements' for name in
            ['B0_line_loading_heatmap','global_TopK','AIDC_P_sensitivity','MESS_PQ_sensitivity','three_pilot_comparison']},
        original_rating_loading_colors_used=False,reason='No admitted operating AC; topology uses feeder colors only'))


if __name__=='__main__':main()
