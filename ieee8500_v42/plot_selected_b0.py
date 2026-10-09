"""Scientific figures of the actual selected96slot B0, without policy claims."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from .common import REPORT, read, write, receipt
from .geometry import read_csv


def run():
    folder=REPORT/'joint_selection_v3/selected_ac/bg0p552_gpu1p0'
    rows=read_csv(folder/'SLOT_ELECTRICAL_SUMMARY.csv')
    taps=read_csv(folder/'REGCONTROL_TAPS.csv')
    figures=REPORT/'figures';figures.mkdir(exist_ok=True)
    x=np.arange(96)/4
    fig,ax=plt.subplots(3,1,figsize=(12,10),sharex=True,layout='constrained')
    ax[0].plot(x,[float(r['Vmax']) for r in rows],label='maximum of all8531 original nodes',color='#c63340')
    ax[0].plot(x,[float(r['Vmin']) for r in rows],label='minimum',color='#315aa7')
    ax[0].axhline(1.05,color='black',linestyle='--',linewidth=1,label='original voltage limits')
    ax[0].axhline(.95,color='black',linestyle='--',linewidth=1)
    ax[0].set(ylabel='Voltage (pu)',ylim=(.945,1.057));ax[0].legend(fontsize=9,ncol=2)
    ax[0].set_title('Selected research B0: original automatic controls; operational voltage gate FAIL',fontweight='bold')
    ax[1].plot(x,[float(r['rho_max']) for r in rows],label='overall canonical line maximum',color='#143e6b')
    ax[1].plot(x,[float(r['transformer_nameplate_kva_rho_max']) for r in rows],label='strict CT winding nameplate maximum',color='#ae6b24')
    ax[1].axhline(1,color='black',linestyle='--',linewidth=1)
    ax[1].set(ylabel='Original rating ratio',ylim=(0,1.06));ax[1].legend(fontsize=9)
    names=sorted({r['name'] for r in taps})
    mat=np.array([[int(next(r['tap_number'] for r in taps if r['name']==n and int(r['slot'])==t)) for t in range(96)] for n in names])
    im=ax[2].imshow(mat,aspect='auto',extent=(-.125,23.875,len(names)-.5,-.5),vmin=-16,vmax=16,cmap='RdBu_r')
    ax[2].set_yticks(np.arange(len(names)),names,fontsize=8)
    ax[2].set(xlabel='Hour (already-exposed development inputs)',ylabel='Original RegControl')
    fig.colorbar(im,ax=ax[2],label='Settled tap number')
    for aa in ax:aa.grid(axis='x',alpha=.15)
    png=figures/'SELECTED_B0_VOLTAGE_LOADING_TAPS.png';svg=png.with_suffix('.svg')
    fig.savefig(png,dpi=160);fig.savefig(svg);plt.close(fig)
    axes=read(folder/'AC_AXES.json');a=np.load(folder/'AC_96.npz',allow_pickle=False)
    targets=read(REPORT/'joint_selection_v3/selection_scores/PREREGISTRATION.json')['targets']
    maxima=[]
    for line in targets:
        idx=[k for k,r in enumerate(axes['lines']) if r['element'].lower()==line and axes['objective_mask'][k]]
        maxima.append(float(a['line_rho'][:,idx].max()))
    fig,ax=plt.subplots(figsize=(12,8),layout='constrained')
    order=np.arange(len(targets));ax.barh(order,maxima,color='#456e93')
    ax.set_yticks(order,[r.replace('line.','') for r in targets],fontsize=9);ax.invert_yaxis()
    ax.axvline(1,color='#c63340',linestyle='--',linewidth=1)
    ax.set(xlabel='Maximum canonical current / original NormalAmps across96 B0 slots',xlim=(0,1.06),
           title='Predeclared20 congestion targets in selected research B0 (no MESS dispatch)')
    for i,value in enumerate(maxima):ax.text(value+.009,i,f'{value:.5f}',va='center',fontsize=8)
    ax.grid(axis='x',alpha=.2)
    png2=figures/'SELECTED_B0_TOP20_ORIGINAL_LINE_RATIOS.png';svg2=png2.with_suffix('.svg')
    fig.savefig(png2,dpi=160);fig.savefig(svg2);plt.close(fig)
    write(figures/'SELECTED_B0_FIGURE_RECEIPT.json',dict(status='ACTUAL_ARCHIVED_B0_SCIENTIFIC_FIGURES',
        data=receipt(folder/'AC_96.npz'),files=[receipt(f) for f in (png,svg,png2,svg2)],
        global_voltage_FAIL=True,no_Bpolicy_performance_claim=True))


if __name__=='__main__':run()
