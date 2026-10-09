"""Scientific figures from saved source/AC CSV; no image-generation model."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .common import *

FIG=REPORT/'figures'


def save(fig,name):
    fig.savefig(FIG/(name+'.svg'),bbox_inches='tight')
    fig.savefig(FIG/(name+'.png'),dpi=150,bbox_inches='tight')
    plt.close(fig)


def format_axis(ax,ylabel):
    ax.set(xlim=(0,24),xlabel='Interval start (fixed AEST, hours)',ylabel=ylabel)
    ax.set_xticks(np.arange(0,25,3));ax.grid(alpha=.22)


def run():
    FIG.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none'})
    t=np.arange(96)/4
    alignment=pd.read_csv(REPORT/'AEMO_PV_96SLOT_ALIGNMENT.csv')
    plan=pd.read_csv(REPORT/'B0_PLANNING_AC_96.csv')
    actual=pd.read_csv(REPORT/'ac/FINAL_B0_ACTUAL/SLOTS.csv')
    old=pd.read_csv(REPORT/'ac/STATIC_PR193_P0/SLOTS.csv')
    for field,label,title,name in [('demand','VIC1 regional demand (MW)','AEMO VIC1: D-1 forecast and Actual, 2025-05-01','01_AEMO_DEMAND'),
                                  ('PV','Regional rooftop PV estimate (MW)','AEMO rooftop PV: same installed capacity, independent profiles','02_ROOFTOP_PV')]:
        fig,ax=plt.subplots(figsize=(11,4))
        for prefix,color in [('Forecast','#276db1'),('Actual','#c56d23')]:
            ax.step(t,alignment[prefix+'_'+field+'_MW'],where='post',label=prefix,color=color)
        ax.set_title(title);format_axis(ax,label);ax.legend()
        fig.text(.12,-.03,'15-minute interval powers; raw 30-minute repeat / 5-minute mean preserves energy. Development day.',fontsize=8)
        save(fig,name)
    fig,ax=plt.subplots(figsize=(11,4.5))
    for frame,style,stage in [(plan,'-','Planning'),(actual,'--','Actual')]:
        for field,color in [('rho_max','#232f40'),('Primary_rho_max','#287da1'),('Triplex_rho_max','#c25c31')]:
            ax.plot(t,frame[field],style,color=color,label=stage+' '+field.replace('_rho_max','').replace('rho_max','all Lines'),lw=1.5)
    ax.axhline(1,color='crimson',lw=1,label='Original thermal ceiling')
    ax.set_title('P5: full canonical objective, Primary and Triplex (all Lines = Triplex)')
    format_axis(ax,'Maximum current / original NormalAmps (pu)');ax.legend(ncol=3,fontsize=8)
    save(fig,'03_LINE_LOADING_96')
    fig,(a,b)=plt.subplots(2,1,figsize=(11,5),sharex=True)
    for frame,style,label in [(plan,'-','Planning'),(actual,'--','Actual')]:
        a.plot(t,frame.binding_local_node,style,label=label+' local hot node',lw=2)
        b.plot(t,frame.rho_max,style,label=label)
    a.set(ylim=(.5,2.5),yticks=[1,2],ylabel='Local Triplex hot node',title='Binding Line.tpx21459660c0: 96/96 slots, no line changes')
    a.legend();a.grid(alpha=.2);b.legend();format_axis(b,'Binding line rho (pu)')
    fig.text(.12,-.025,'Local hot1/2 are split-phase labels, not MV phase A/B. Original primary phase is retained in TOP20 CSV.',fontsize=8)
    save(fig,'04_BINDING_LINE_PHASE')
    fig,ax=plt.subplots(figsize=(11,4.5))
    ax.axhspan(.95,1.05,color='#b4d5b7',alpha=.3,label='Unchanged allowed band')
    for frame,style,stage in [(plan,'-','Planning'),(actual,'--','Actual')]:
        ax.plot(t,frame.Vmin,style,color='#247d93',label=stage+' Vmin')
        ax.plot(t,frame.Vmax,style,color='#c56539',label=stage+' Vmax')
    p3=pd.read_csv(REPORT/'ac/B0_PLANNING/SLOTS.csv')
    ax.plot(t,p3.Vmax,':',color='#a32031',label='P3 Planning Vmax (FAIL)')
    ax.axhline(1.05,color='crimson',lw=1);ax.axhline(.95,color='crimson',lw=1)
    ax.set_title('Original 8,531-node voltage envelope: P5 strict violations = 0')
    format_axis(ax,'Node voltage (pu)');ax.legend(ncol=3,fontsize=8);save(fig,'05_VOLTAGE_ENVELOPE')
    states=pd.read_csv(REPORT/'REGCONTROL_CAPCONTROL_STATE_96.csv')
    final=states[states.stage.isin(['FINAL_B0_PLANNING','FINAL_B0_ACTUAL'])]
    names=sorted(final[final.kind=='RegControl'].name.unique())+sorted(final[final.kind=='Capacitor'].name.unique())
    fig,axs=plt.subplots(6,4,figsize=(16,15),sharex=True)
    for ax,name in zip(axs.flat,names):
        for stage,style,color in [('FINAL_B0_PLANNING','-','#276db1'),('FINAL_B0_ACTUAL','--','#c56d23')]:
            frame=final[(final.stage==stage)&(final.name==name)].sort_values('slot')
            value=frame.tap_number if frame.kind.iloc[0]=='RegControl' else frame.energized.astype(str).str.lower().eq('true').astype(int)
            ax.step(t,value,where='post',ls=style,color=color,lw=1.2)
        ax.set_title(name,fontsize=9);ax.grid(alpha=.2);ax.set_xticks([0,6,12,18,24])
        ax.set_ylabel('tap number' if name.startswith(('feeder','vreg')) else 'ON state',fontsize=8)
        if name.startswith('capbank'):ax.set_yticks([0,1]);ax.set_ylim(-.1,1.1)
    for ax in axs.flat[len(names):]:ax.axis('off')
    axs.flat[-1].text(0,.9,'Blue: Planning\nOrange dashed: Actual\n12 original RegControls\n10 original capacitor objects\nCAPBank3 retained OFF\n9 original automatic CapControls\nOriginal delays / limits preserved',va='top',fontsize=10)
    fig.suptitle('P5 independent automatic tap trajectories and capacitor switching states',y=.995,fontsize=15)
    fig.supxlabel('Interval start (fixed AEST, hours)');fig.tight_layout(rect=(0,.02,1,.98));save(fig,'06_REGCONTROL_CAPACITORS')
    fig,axs=plt.subplots(1,2,figsize=(12,4.5))
    for ax,field,title in zip(axs,('rho_max','Primary_rho_max'),('All original Lines (Triplex binding)','Primary Lines')):
        ax.plot(t,old[field],label='PR193 static / P0 / PV0',color='#777')
        ax.plot(t,plan[field],label='P5 AEMO / PV Planning',color='#276db1')
        ax.plot(t,actual[field],'--',label='P5 AEMO / PV Actual',color='#c56d23')
        ax.set_title(title);format_axis(ax,'Maximum loading (pu)');ax.legend(fontsize=8)
    fig.suptitle('Different inputs and control policies: not B2/B3 algorithm improvement',fontsize=12)
    fig.tight_layout();save(fig,'07_STATIC_VS_TIME_SERIES')
    x=pd.read_csv(REPORT/'FINAL_PCC_PQ_CONTROLLABILITY.csv')
    order=x.groupby('line').base_rho.max().sort_values(ascending=False).index
    fig,axs=plt.subplots(1,2,figsize=(17,8))
    for ax,field,title in zip(axs,('d_rho_d_consumption_kw','d_rho_d_consumption_kvar'),('P derivative / kW consumption','Q derivative / kvar consumption')):
        matrix=x.pivot_table(index='PCC',columns='line',values=field,aggfunc='mean').loc[:,order]
        bound=float(np.abs(matrix).max().max())
        im=ax.imshow(matrix,cmap='RdBu_r',vmin=-bound,vmax=bound,aspect='auto')
        ax.set_yticks(range(len(matrix)),matrix.index);ax.set_xticks(range(len(order)),[n.replace('Line.','') for n in order],rotation=90,fontsize=8)
        ax.set_title(title);fig.colorbar(im,ax=ax,label='Mean fixed-tap d rho / unit (96 slots)',shrink=.65)
    fig.suptitle('P5 local AC derivatives: independent of policy solver performance',fontsize=13)
    fig.tight_layout();save(fig,'08_PCC_SENSITIVITY_HEATMAP')
    write(REPORT/'FIGURE_RECEIPT.json',dict(figures=[receipt(p) for p in sorted(FIG.glob('*'))],
        Python_only=True,generative_image_calls=0,data_source='final P5 saved CSV; prior P3 voltage and PR193 static comparison'))
    print('8 scientific SVG/PNG figure pairs generated',flush=True)


if __name__=='__main__':run()
