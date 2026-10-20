"""Measured-only Matplotlib/SVG figures; missing coordinates are never invented."""
from .preflight import *
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

def figures():
    dest=DOC/'figures';dest.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','savefig.dpi':220})
    traffic=pd.read_csv(DOC/'ORIGINAL_TRAFFIC_SERVICES.csv')
    nodes=pd.read_csv(DOC/'ORIGINAL_TRAFFIC_NODES.csv')
    links=pd.read_csv(RUNTIME/'traffic/link_order_509.csv')
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text());by={b['bus']:b for b in inv['buses']}
    mapping=pd.read_csv(DOC/'CKT24_SERVICE_SITE_MAPPING.csv') if (DOC/'CKT24_SERVICE_SITE_MAPPING.csv').exists() else None
    if mapping is not None:mapping=mapping.dropna(subset=['e_x','e_y'])
    colors={r.service_id:plt.get_cmap('tab20')(i%20) for i,r in enumerate(traffic.itertuples())}
    def savefig(fig,name):
        fig.savefig(dest/(name+'.svg'),bbox_inches='tight');fig.savefig(dest/(name+'.png'),bbox_inches='tight');plt.close(fig)
    def labels(ax,frame,x,y):
        for r in frame.to_dict('records'):
            marker='o' if r['type']=='IDC' else '^'
            ax.scatter(r[x],r[y],color=colors[r['service_id']],s=38,marker=marker,edgecolor='black',lw=.4,zorder=3)
            ax.annotate(r['service_id'],(r[x],r[y]),xytext=(3,3),textcoords='offset points',fontsize=6)
    def road(ax):
        lookup={int(r.transport_node_id.split('_')[1]):(r.x,r.y) for r in nodes.itertuples()}
        edges=[(lookup[int(r.from_node)],lookup[int(r.to_node)]) for r in links.itertuples()]
        ax.add_collection(LineCollection(edges,colors='#a6b1ba',lw=.45,alpha=.6));ax.autoscale()
        labels(ax,traffic,'x','y');ax.set(xlabel='Original SUMO X (m)',ylabel='Original SUMO Y (m)');ax.set_aspect('equal')
    def grid(ax):
        edges=[]
        for r in inv['lines']:
            a,b=[by[r[k].split('.')[0].lower()] for k in ['bus1','bus2']]
            if a['coord_defined'] and b['coord_defined']:edges.append([(a['x'],a['y']),(b['x'],b['y'])])
        ax.add_collection(LineCollection(edges,colors='#929da8',lw=.45,alpha=.8));ax.autoscale()
        if mapping is not None:labels(ax,mapping,'e_x','e_y')
        ax.set(xlabel='Original EPRI X (coordinate units)',ylabel='Original EPRI Y (coordinate units)');ax.set_aspect('equal')
        ax.ticklabel_format(style='plain',useOffset=False)
    fig,ax=plt.subplots(figsize=(9,7));road(ax);ax.set_title('Unchanged traffic graph: 12 IDC + 12 STA');savefig(fig,'02_original_traffic')
    fig,ax=plt.subplots(figsize=(9,7));grid(ax)
    missing=sum(not b['coord_defined'] for b in inv['buses'])
    ax.set_title(f'Ckt24 original drawing coordinates; {missing:,} unlocated buses omitted\nProvisional mapping; PCC hardware and GIS authority unverified')
    savefig(fig,'01_ckt24_original_coordinates')
    fig,axs=plt.subplots(1,2,figsize=(14,6));road(axs[0]);grid(axs[1])
    axs[0].set_title('Original traffic XY');axs[1].set_title('Original Ckt24 XY; provisional order witness')
    savefig(fig,'03_relative_direction_comparison')
    top=pd.read_csv(DOC/'B0_MV_LV_BOTTLENECKS.csv').groupby(['line','phase','voltage_class']).loading_pu.max().nlargest(20).sort_values()
    fig,ax=plt.subplots(figsize=(9,6));ax.barh([f'{a} / ph{b} ({c})' for a,b,c in top.index],top.values,
        color=['#285e8e' if c=='MV' else '#b26b30' for _,_,c in top.index]);ax.set(xlabel='Maximum phase current / original NormAmps',
        title='Original background only: Top 20 line/phase peaks (not final B0)');savefig(fig,'04_original_top20')
    sens=pd.read_csv(DOC/'MESS_PQ_CONTROLLABILITY.csv')
    def column(r):return ('P+' if r.p_kw>0 else 'P-') if r.p_kw else ('Q+' if r.q_kvar>0 else 'Q-')
    sens['direction']=[column(r) for r in sens.itertuples()]
    heat=sens.pivot(index='bus',columns='direction',values='delta_rho')[['P+','P-','Q+','Q-']]
    order=heat.abs().max(axis=1).nlargest(32).index;heat=heat.loc[order]
    fig,ax=plt.subplots(figsize=(7,9));lim=float(abs(heat).max().max());im=ax.imshow(heat,aspect='auto',cmap='RdBu_r',vmin=-lim,vmax=lim)
    ax.set_xticks(range(4),heat.columns);ax.set_yticks(range(len(heat)),heat.index,fontsize=6)
    ax.set_title('Fresh AC virtual MV ports: largest 32 responses\nP = ±30 kW; Q = ±25 kvar; negative Δρ is reduction')
    fig.colorbar(im,ax=ax,label='Change in whole-network maximum loading (pu)');savefig(fig,'05_virtual_mess_pq_sensitivity')
    ratios=pd.read_csv(DOC/'POWER_RATIO_SCREENING.csv');fig,axs=plt.subplots(1,2,figsize=(11,4))
    names=[f'BG {r.k_BG:g}\n{r.mode}' for r in ratios.itertuples()]
    axs[0].bar(names,ratios.transformer_max,color='#587c98');axs[0].axhline(1,color='red',lw=1);axs[0].set(ylabel='Worst transformer kVA / rating')
    axs[1].bar(names,ratios.v_max-1.05,color='#b3764f');axs[1].axhline(0,color='red',lw=1);axs[1].set(ylabel='Maximum voltage minus 1.05 pu')
    fig.suptitle('Predeclared background-only scenarios; no final scenario selected');savefig(fig,'06_background_scenario_gates')
    save('FIGURE_SCOPE.json',dict(figures=sorted(p.name for p in dest.glob('*.svg')),
        actual_AIDC_schedule_heatmap='NOT_GENERATED_NO_FEASIBLE_SCHEDULE_WITNESS',
        final_B0_B3_comparison='NOT_GENERATED_PRE_SOLVER_GATES_NOT_PASSED',
        solver_scalability='NOT_GENERATED_NO_CKT24_MILP_MEASUREMENTS',
        unavailable_coordinates_are_never_synthesized=True))

if __name__=='__main__':figures()
