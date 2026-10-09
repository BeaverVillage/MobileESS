"""Six reproducible SVG/PNG scientific comparisons; no image-generation API."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .common import *
from .report import folder, case_arrays, line_groups


def run():
    out=REPORT/'figures';out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none',
        'axes.grid':True,'grid.alpha':.2,'savefig.facecolor':'white'})
    colors={'Unbalanced':'#576882','Balanced':'#d65f24'}
    sources=('PLANNING','ACTUAL'); saved=[]
    def save(fig,name):
        fig.tight_layout(rect=(0,.02,1,.97))
        for suffix in ('svg','png'):
            p=out/(name+'.'+suffix);fig.savefig(p,dpi=180);saved.append(receipt(p))
        plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(11,4),sharey=True)
    for axis,source in zip(ax,sources):
        for offset,model in ((-.18,'Unbalanced'),(.18,'Balanced')):
            r=read(folder(model,source)/'RECEIPT.json')
            values=[r[k] for k in ('rho_max','Primary_rho_max','Triplex_rho_max')]
            bars=axis.bar(np.arange(3)+offset,values,.35,label=model,color=colors[model])
            for bar,v in zip(bars,values):axis.text(bar.get_x()+bar.get_width()/2,v+.013,f'{v:.4f}',ha='center',fontsize=9)
        axis.set_xticks(range(3),['All lines','Primary','Triplex']);axis.set_title(source.title())
        axis.axhline(1,color='#a02a2a',ls='--',lw=1);axis.set_ylim(0,1.06);axis.set_ylabel('Daily maximum loading (pu)')
        axis.legend(frameon=False)
    fig.suptitle('Official customer load-model comparison — same P5, total P/Q and per-hot PV')
    save(fig,'01_balanced_unbalanced_max_loading')
    fig,ax=plt.subplots(2,1,figsize=(11,6),sharex=True)
    hours=np.arange(96)/4
    for axis,source in zip(ax,sources):
        df=pd.read_csv(folder('Balanced',source)/'SLOTS.csv')
        axis.plot(hours,df.Primary_rho_max,label='Balanced Primary',color='#2c6583',lw=2)
        axis.plot(hours,df.Triplex_rho_max,label='Balanced Triplex',color='#d65f24',lw=2)
        old=pd.read_csv(folder('Unbalanced',source)/'SLOTS.csv')
        axis.plot(hours,old.Triplex_rho_max,label='Unbalanced Triplex',color='#808080',ls=':',lw=1.5)
        axis.set_title(source.title());axis.set_ylabel('Canonical max loading (pu)');axis.legend(ncol=3,frameon=False)
    ax[-1].set_xticks(np.arange(0,25,3));ax[-1].set_xlabel('2025-05-01 interval start, AEST hour')
    save(fig,'02_primary_triplex_96slots')
    fig,ax=plt.subplots(1,2,figsize=(14,9))
    for axis,source in zip(ax,sources):
        axes,z=case_arrays('Balanced',source);_,old=case_arrays('Unbalanced',source);groups=line_groups(axes)
        names=sorted(groups,key=lambda n:(-float(z['line_rho'][:,groups[n]].max()),n))[:20]
        new=[float(z['line_rho'][:,groups[n]].max()) for n in names];prior=[float(old['line_rho'][:,groups[n]].max()) for n in names]
        y=np.arange(20);axis.barh(y-.18,prior,.34,label='Unbalanced',color=colors['Unbalanced'])
        axis.barh(y+.18,new,.34,label='Balanced',color=colors['Balanced'])
        axis.set_yticks(y,[n.removeprefix('Line.') for n in names],fontsize=8);axis.invert_yaxis()
        axis.set_xlabel('Maximum across96 (pu)');axis.set_title(source.title()+' — Balanced top20, identical line comparison')
        axis.legend(frameon=False);axis.set_xlim(0,.65)
    save(fig,'03_top20_identical_lines')
    fig,ax=plt.subplots(2,1,figsize=(11,6),sharex=True,sharey=True)
    for axis,source in zip(ax,sources):
        for model in ('Unbalanced','Balanced'):
            df=pd.read_csv(folder(model,source)/'SLOTS.csv');ls='--' if model=='Unbalanced' else '-'
            axis.plot(hours,df.Vmin,color=colors[model],ls=ls,label=model+' Vmin')
            axis.plot(hours,df.Vmax,color=colors[model],ls=ls,label=model+' Vmax')
        axis.axhline(.95,color='#a02a2a',ls=':');axis.axhline(1.05,color='#a02a2a',ls=':');axis.set_ylim(.947,1.053)
        axis.set_title(source.title()+' — all 8531 nodes');axis.set_ylabel('Voltage (pu)');axis.legend(ncol=4,fontsize=9,frameon=False)
    ax[-1].set_xlabel('2025-05-01 interval start, AEST hour');ax[-1].set_xticks(np.arange(0,25,3))
    save(fig,'04_all_node_voltage_envelopes')
    fig,ax=plt.subplots(2,1,figsize=(12,6),sharex=True)
    bind=pd.read_csv(REPORT/'BINDING_LINE_96SLOT.csv')
    names=sorted(bind.binding_line.unique());code={n:i for i,n in enumerate(names)}
    for axis,source in zip(ax,sources):
        for model in ('Unbalanced','Balanced'):
            df=bind[(bind.source==source)&(bind.model==model)]
            axis.step(hours,[code[n] for n in df.binding_line],where='post',label=model,color=colors[model],lw=2,
                ls='--' if model=='Unbalanced' else '-')
        axis.set_yticks(range(len(names)),[n.removeprefix('Line.') for n in names],fontsize=9)
        axis.set_title(source.title());axis.legend(frameon=False);axis.set_ylim(-.4,len(names)-.6)
    ax[-1].set_xlabel('2025-05-01 interval start, AEST hour');ax[-1].set_xticks(np.arange(0,25,3))
    save(fig,'05_binding_line_changes')
    fig,ax=plt.subplots(2,1,figsize=(11,6),sharex=True,sharey=True)
    for axis,source in zip(ax,sources):
        for model in ('Unbalanced','Balanced'):
            axes,z=case_arrays(model,source)
            for hot in (1,2):
                indices=[i for i,r in enumerate(axes['lines']) if r['element']=='Line.tpx21459660c0' and r['objective_included'] and r['node']==hot]
                assert len(indices)==1
                axis.plot(hours,z['line_amps'][:,indices[0]],label=model+' hot'+str(hot),color=colors[model],ls='-' if hot==1 else '--')
        axis.axhline(156,color='#a02a2a',ls=':',label='Original 156 A rating')
        axis.set_title(source.title()+' — tpx21459660c0, parent terminal');axis.set_ylabel('Hot current (A)')
        axis.legend(ncol=3,frameon=False,fontsize=9);axis.set_ylim(0,165)
    ax[-1].set_xlabel('2025-05-01 interval start, AEST hour');ax[-1].set_xticks(np.arange(0,25,3))
    save(fig,'06_old_binding_triplex_hot_currents')
    write(REPORT/'FIGURE_RECEIPT.json',dict(Python_matplotlib=True,AI_image_generation=False,figures=6,SVG_PNG_pairs=6,files=saved))
    print('six scientific SVG/PNG pairs saved',flush=True)


if __name__=='__main__':run()
