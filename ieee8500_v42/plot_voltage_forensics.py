"""Plot exported AC evidence; can run in a separate Matplotlib-only runtime."""
import csv
import os
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    docs=root/'docs/ieee8500_v42_single_case'
    cache=root/'ieee8500_v42/outputs/matplotlib_cache'
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(cache))
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams['svg.hashsalt']='ieee8500_v42_original_voltage_path'
    import matplotlib.pyplot as plt
    with (docs/'LOWEST_VOLTAGE_PATH.csv').open(encoding='utf-8-sig',newline='') as file:
        path=list(csv.DictReader(file))
    x=list(range(len(path)+1))
    y=[float(path[0]['v_in_pu'])]+[float(r['v_out_pu']) for r in path]
    cy=[float(path[0]['counter_v_in_pu'])]+[float(r['counter_v_out_pu']) for r in path]
    fig,ax=plt.subplots(figsize=(12,4.8))
    ax.plot(x,y,label='Original BG=1.0, no AIDC/MESS',lw=2,color='#bc551d')
    ax.plot(x,cy,label='BG=0.552 causal diagnostic only',lw=1.8,color='#185da3')
    ax.axhline(.95,color='#a82238',ls='--',lw=1,label='V42 voltage lower limit 0.95')
    ax.set(xlabel='Original upstream path element index',ylabel='Tracked phase/hot voltage (pu)',
        title='Original IEEE8500 lowest-voltage customer path',ylim=(.900,1.065))
    ax.annotate('Service transformer + triplex',xy=(127,y[-1]),xytext=(76,.916),fontsize=9,
        arrowprops={'arrowstyle':'->','color':'#444'})
    ax.grid(alpha=.22);ax.legend(loc='lower left',bbox_to_anchor=(.02,.16),fontsize=9)
    fig.tight_layout()
    fig.savefig(docs/'ORIGINAL_LOWEST_VOLTAGE_PATH.svg',metadata={'Date':None})
    fig.savefig(docs/'ORIGINAL_LOWEST_VOLTAGE_PATH.png',dpi=180)
    plt.close(fig)
    print('Original voltage path PNG + SVG generated from exported real AC evidence')


if __name__=='__main__':
    main()
