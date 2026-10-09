"""Render measured initialization comparisons and FULL-verified dispatch only."""
from pathlib import Path
import json,os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
plt.rcParams.update({'font.family':['Malgun Gothic','DejaVu Sans'],'axes.unicode_minus':False,'font.size':10})

def save(fig,name):
    figures=HERE/'figures';figures.mkdir(exist_ok=True)
    fig.savefig(figures/(name+'.png'),dpi=180,bbox_inches='tight')
    fig.savefig(figures/(name+'.svg'),bbox_inches='tight');plt.close(fig)

def main():
    data=json.loads((HERE/'MEASURED_COMPARISON.json').read_text(encoding='utf-8'))
    rows=data['comparison'];labels=[r['label'] for r in rows]
    native=[r['initialization_Native_Runtime'] for r in rows]
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,key,title in ((axes[0],'initialization_Native_Runtime','첫 FULL 통과까지 Native Runtime'),(axes[1],'first_FULL_wall_seconds','모델 생성 포함 첫 FULL 통과 wall')):
        values=[r.get(key) for r in rows]
        for i,(r,value) in enumerate(zip(rows,values)):
            if value is None:
                ax.text(i,0,'UNKNOWN' if r['FULL_PASS'] else '초기해 없음',rotation=90,va='bottom',ha='center');continue
            bar=ax.bar(i,value,color='#176f73' if r['FULL_PASS'] else '#a9adb6',hatch=None if r['FULL_PASS'] else '//')
            ax.text(i,value,f'{value:.2f}s'+(' (초기해 없음)' if not r['FULL_PASS'] else ''),ha='center',va='bottom',fontsize=8)
        ax.set_xticks(range(len(rows)),labels,rotation=25,ha='right');ax.set_ylabel('seconds');ax.set_title(title)
        ax.set_xlim(-.6,len(rows)-.4)
        ax.margins(y=.2);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('V42 B2 초기해 실측 — 실패 시 종료까지 사용시간 표시, 보장된 개선값 아님')
    fig.tight_layout();save(fig,'01_first_full_time')
    fig,ax=plt.subplots(figsize=(13,5));colors=plt.cm.tab20.colors
    for i,r in enumerate(rows):
        left=0.
        for k,c in enumerate(r['Native_calls']):
            ax.barh(i,c['Native_Runtime'],left=left,color=colors[k%len(colors)],edgecolor='white')
            if c['Native_Runtime']>25:ax.text(left+c['Native_Runtime']/2,i,c['track'],ha='center',va='center',fontsize=8)
            left+=c['Native_Runtime']
        ax.text(left+2,i,f'{left:.2f}s',va='center')
    ax.set_yticks(range(len(rows)),labels);ax.set_xlabel('초기화 단계별 Native seconds');ax.grid(axis='x',alpha=.2)
    ax.set_title('실제 LP/MILP 호출 합산 · 최초 FULL 통과 이후 호출 제외');fig.tight_layout();save(fig,'02_stage_native_runtime')
    old=next(r for r in rows if r['label']=='May03 V18R2');new=next(r for r in rows if r['label']=='May03 V19')
    fig,ax=plt.subplots(figsize=(8,4));values=[old['initialization_Native_Runtime'],new['initialization_Native_Runtime']]
    bars=ax.bar(['May03 V18R2','May03 V19'],values,color=['#a9adb6','#176f73']);bars[0].set_hatch('//')
    for i,r in enumerate((old,new)):
        ax.text(i,values[i],f'{values[i]:.3f}s\n'+('FULL PASS' if r['FULL_PASS'] else '첫 초기해 없음 · 안전 중단'),ha='center',va='bottom')
    ax.set_ylim(0,max(values)*1.3);ax.set_ylabel('Native seconds');ax.set_title('동일 날짜·입력·원본 matrix/domain 비교');fig.tight_layout();save(fig,'03_may03_v18_v19')
    packet=HERE/'MAY03_INITIAL_POINT_DISPATCH.json'
    if not packet.exists():return
    dispatch=json.loads(packet.read_text(encoding='utf-8'));assert dispatch['original_FULL_replay_PASS']
    fig,axes=plt.subplots(4,4,figsize=(16,11));vehicles=dispatch['vehicles']
    for row,(unit,v) in enumerate(vehicles.items()):
        t=np.arange(96)/4.;soc=np.arange(97)/4.
        axes[row,0].step(t,v['P_kW'],where='post',color='#176f73');axes[row,0].set_ylabel(unit+'\nP (kW)')
        axes[row,1].step(t,v['Q_kvar'],where='post',color='#945da8');axes[row,1].set_ylabel('Q (kvar)')
        axes[row,2].plot(soc,v['SOC_kWh'],color='#cf8421');axes[row,2].set_ylabel('SOC (kWh)')
        sites=list(dict.fromkeys(v['location']));codes=[sites.index(s) for s in v['location']]
        axes[row,3].step(t,codes,where='post',color='#41546c');axes[row,3].set_yticks(range(len(sites)),sites);axes[row,3].set_ylabel('연결 장소 / 이동')
        for ax in axes[row]:ax.set_xlim(0,24);ax.set_xlabel('시간 (hour)');ax.grid(alpha=.2)
    fig.suptitle('May03 원본 FULL 검증 통과 초기해 · P=Pdis-Pch · clipping/rounding/repair 없음\npoint SHA '+dispatch['selected_point_SHA'][:20])
    fig.tight_layout(rect=(0,0,1,.95));save(fig,'04_may03_vehicle_dispatch')

if __name__=='__main__':main()
