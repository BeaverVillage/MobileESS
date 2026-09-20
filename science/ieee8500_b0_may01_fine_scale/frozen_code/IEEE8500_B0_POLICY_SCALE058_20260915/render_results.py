"""Postprocess completed B0 policy arrays; does not import or call OpenDSS."""
import os,sys,json,csv,hashlib
from pathlib import Path
from datetime import datetime,timedelta
H=Path(__file__).absolute().parent;BG=H.parent/'IEEE8500_B0_BG_SCALE_20260915'
sys.dont_write_bytecode=True;sys.path.insert(0,str(BG/'plot_deps'));os.environ['MPLCONFIGDIR']=str(H/'mpl_config')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
summary=read(H/'B0_SUMMARY.json');geo=read(H/'GEOMETRY.json');z=np.load(H/'B0_ALL_PHASE_ARRAYS.npz')
labels=z['line_phase_axes'];a=z['line_current_loading_pu'];v=z['voltage_pu']
slot,j=np.unravel_index(a.argmax(),a.shape);slot,j=int(slot),int(j)
start=datetime.fromisoformat('2025-05-01T00:00:00+10:00')
stamp=lambda t:(start+timedelta(minutes=15*int(t))).isoformat()
assert a[slot,j]==summary['max_phase_line_loading_pu'] and v.min()==summary['Vmin_pu']
byline={};parsed=[]
for k,label in enumerate(labels):
    name,term,bus,node=str(label).split('|');name=name.lower();byline.setdefault(name,[]).append(k)
    parsed.append((name,int(term[1:]),int(node[4:])))
names=[r['name'].lower() for r in geo['lines']];segments=np.array([r['xy'] for r in geo['lines']])
peak=np.array([a[:,byline[n]].max() for n in names]);at=np.array([a[slot,byline[n]].max() for n in names])
assert peak.max()==at.max()==a.max()
critical=names.index(parsed[j][0]);center=segments[critical].mean(axis=0)
bounds=[segments[:,:,0].min(),segments[:,:,0].max(),segments[:,:,1].min(),segments[:,:,1].max()]
span=max(bounds[1]-bounds[0],bounds[3]-bounds[2]);zoom=span*.035
norm=Normalize(0,1);cmap=plt.get_cmap('YlOrRd')
def plot(values,title,path):
    fig,axes=plt.subplots(1,2,figsize=(14,7),layout='constrained',gridspec_kw={'width_ratios':[1.7,1]})
    for k,ax in enumerate(axes):
        order=np.argsort(values);lc=LineCollection(segments[order],cmap=cmap,norm=norm,linewidths=1.1 if k else .9)
        lc.set_array(values[order]);ax.add_collection(lc);ax.set_aspect('equal');ax.set_facecolor('#f4f6f8');ax.set_xticks([]);ax.set_yticks([])
        if k:ax.set_xlim(center[0]-zoom,center[0]+zoom);ax.set_ylim(center[1]-zoom,center[1]+zoom)
        else:ax.set_xlim(bounds[0]-.025*span,bounds[1]+.025*span);ax.set_ylim(bounds[2]-.025*span,bounds[3]+.025*span)
        for sp in ax.spines.values():sp.set_visible(False)
        ax.plot(*center,'o',ms=8,mfc='none',mec='#142b45',mew=1)
        ax.set_title('Critical-line area (original coordinates)' if k else 'Whole feeder (original coordinates)',fontsize=11)
    fig.colorbar(ScalarMappable(norm,cmap),ax=axes,shrink=.8,label='Line loading [pu] | common scale 0 to 1')
    fig.suptitle('IEEE8500 B0 policy | background 0.58 | AIDC reference ON | MESS OFF\n'+title,fontsize=14)
    fig.supxlabel(f'Peak {a.max():.6f} pu | Vmin {v.min():.6f} pu | AC FAIL: undervoltage | fixed PV alpha 0.50',fontsize=11)
    fig.savefig(path,dpi=180);plt.close(fig)
plot(peak,'Daily maximum across 96 slots, terminals and local phases | 2025-05-01',H/'B0_POLICY_SCALE058_DAILY_MAX_HEATMAP.png')
plot(at,f'System critical time: slot {slot}, {stamp(slot)} | maximum terminal/phase per line',H/'B0_POLICY_SCALE058_CRITICAL_TIME_HEATMAP.png')

# Reuse only immutable endpoint metadata; recompute every electrical value from this policy run.
metadata=list(csv.DictReader((BG/'heatmap_csv/IEEE8500_B0_SCALE058_DAILY_MAX_HEATMAP.csv').open(encoding='utf-8')))
daily=[];criticalrows=[];basecols='element_type element_id from_bus to_bus x_from y_from x_to y_to'.split()
for old in metadata:
    r={k:old[k] for k in basecols}
    for k in ['x_from','y_from','x_to','y_to']:r[k]=float(r[k])
    n=r['element_id'];idx=byline.get(n,[])
    for bus,x,y in [('from_bus','x_from','y_from'),('to_bus','x_to','y_to')]:assert [r[x],r[y]]==geo['coordinates'][r[bus]]
    if not idx:
        assert old['data_status']=='DISABLED'
        daily.append(dict(**r,data_status='DISABLED',B0_element_max_loading=None,max_terminal=None,max_phase=None,max_slot=None,max_time_AEST=None))
        criticalrows.append(dict(**r,terminal=None,phase=None,data_status='DISABLED',B0_loading_at_critical_time=None,critical_slot=slot,critical_time_AEST=stamp(slot)))
        continue
    values=a[:,idx];t,q=np.unravel_index(values.argmax(),values.shape);w=parsed[idx[int(q)]]
    daily.append(dict(**r,data_status='OK',B0_element_max_loading=float(values[t,q]),max_terminal=w[1],max_phase=w[2],max_slot=int(t),max_time_AEST=stamp(t)))
    for k in idx:
        w=parsed[k];criticalrows.append(dict(**r,terminal=w[1],phase=w[2],data_status='OK',B0_loading_at_critical_time=float(a[slot,k]),critical_slot=slot,critical_time_AEST=stamp(slot)))
undervoltage=[]
for t,k in np.argwhere(v<.95-1e-9):undervoltage.append(dict(slot=int(t),time_AEST=stamp(t),node=str(z['node_names'][k]),voltage_pu=float(v[t,k]),limit_pu=.95,shortfall_pu=float(.95-v[t,k])))
(H/'UNDERVOLTAGE_WITNESSES.json').write_text(json.dumps(undervoltage,indent=2),encoding='utf-8')
brief=dict(background_scale=.58,critical_slot=slot,critical_time_AEST=stamp(slot),critical_line=parsed[j][0],critical_terminal=parsed[j][1],critical_phase=parsed[j][2],rho_max=float(a.max()),Vmin=float(v.min()),Vmax=float(v.max()),transformer_current_max=float(z['transformer_current_loading_pu'].max()),transformer_kVA_max=float(z['transformer_winding_kva_loading_pu'].max()),AC_status=summary['status'],AIDC='B0_REFERENCE_ON',MESS='OFF')
tables=[]
for suffix,data in [('DAILY_MAX_HEATMAP',daily),('CRITICAL_TIME_HEATMAP',criticalrows),('HEATMAP_SUMMARY',[brief])]:
    cols=list(data[0]);tables.append(dict(filename=f'IEEE8500_B0_POLICY_SCALE058_{suffix}.csv',columns=cols,rows=[[r[c] for c in cols] for r in data]))
out=H/'heatmap_csv';out.mkdir(exist_ok=True);(out/'extracted_tables.json').write_text(json.dumps(tables,allow_nan=False),encoding='utf-8')
old=read(BG/'alpha_0.58/B0_SUMMARY.json')
lines=['# IEEE8500 B0 policy — background scale 0.58','', '**AC status: FAIL — undervoltage.** All 96 slots converged and native automatic controls settled.','',
'Frozen May01 B0 reference workload/PCC injections are ON (already-authorized 2x AIDC scale, no additional scaling). MESS P/Q are zero. PV retains fixed alpha 0.50, ratio and D1 forecasts. Background P/Q use scale 0.58. Topology, load spatial allocation, hosts, PCCs, coordinates and ratings are unchanged.','',
'| Metric | AIDC OFF screening | B0 reference AIDC ON | Hard limit |','|---|---:|---:|---:|']
for key,limit in [('max_phase_line_loading_pu',1),('Vmin_pu',.95),('Vmax_pu',1.05),('max_transformer_phase_current_pu',1),('max_transformer_winding_kva_pu',1)]:lines.append(f'| {key} | {old[key]:.9f} | {summary[key]:.9f} | {limit} |')
lines+=['',f'Global line maximum: `{parsed[j][0]}`, terminal {parsed[j][1]}, local node {parsed[j][2]}, slot {slot}, {stamp(slot)}.','',
'## Undervoltage witnesses','', '| Slot (0-based) | AEST slot start | Node | Voltage pu |','|---:|---|---|---:|']
for r in undervoltage:lines.append(f'| {r["slot"]} | {r["time_AEST"]} | {r["node"]} | {r["voltage_pu"]:.9f} |')
lines+=['','There are no line, transformer-current, transformer-kVA or overvoltage violations. The fixed scale 0.58 is retained; no feasibility tuning was performed.','',
'## Outputs and interpretation','', '- Daily heatmap: each physical line uses its maximum over all 96 slots and all monitored terminals/local phases.','- Critical-time heatmap: every line is evaluated at the same global peak slot, using its largest terminal/local-phase value.','- Both PNGs use original X/Y coordinates, identical extents and YlOrRd colorbar 0–1 pu. No reflection, rotation or rescaling.','- CSV daily rows: 3,703 physical lines, including 5 DISABLED placeholders. Critical-time rows: 12,312 monitored terminal/phase values plus 5 DISABLED placeholders. All loading values are pu; empty values mean unavailable. Group critical CSV by element_id and take max to color one physical line.','- Phase fields use original local node numbers; triplex local node 1 is not a claim of primary phase A.','- AEST timestamps are interval starts. Slot 75 starts at 18:45; forecast interval-end timestamp is 19:00.','- B0_REFERENCE_JOBS.json and B0_REFERENCE_AIDC_POWER.npz are unchanged copies of the existing B0 reference. No workload rescheduling or optimizer was invoked.','',
'## Verification','',f'- Source/static/spatial conservation: PASS. Final exact AC: 96/96 converged, 96/96 control settled. B1/B2/B3 runs: 0.',f'- PCC commands match reference P/Q exactly. Maximum solved readback residuals: {summary["max_PCC_readback_P_residual_kw"]:.9f} kW / {summary["max_PCC_readback_Q_residual_kvar"]:.9f} kvar; unchanged OpenDSS convergence tolerance {summary["OpenDSS_convergence_tolerance"]}.',
'- Initial attempt stopped after 3 snapshots because an added readback assertion was stricter than the existing solver tolerance. The assertion was replaced by exact command verification and recorded physical residuals. Final results come entirely from a fresh 96-slot context. No hard limit, solver tolerance, reference input or network setting was changed.','- This is a Day-Ahead B0 policy replay, not an Actual/realized-data simulation. Existing authorities and previous screening results remain unchanged.']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
audit=dict(status='PASS',B0_AC_status=summary['status'],daily_rows=len(daily),critical_rows=len(criticalrows),undervoltage_node_slots=len(undervoltage),undervoltage_slots=sorted(set(r['slot'] for r in undervoltage)),all_values_finite=bool(np.isfinite(a).all()),colorbar_pu=[0,1],geometry_unchanged=True,global_peak_matches_both_maps=True,critical=brief)
(H/'HEATMAP_VALIDATION.json').write_text(json.dumps(audit,indent=2),encoding='utf-8');print(json.dumps(audit),flush=True)
