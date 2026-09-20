"""Render fine-search arrays with exactly the preceding .58 geometry and extents."""
import os,sys,json,csv,hashlib,shutil
from pathlib import Path
from datetime import datetime,timedelta
H=Path(__file__).absolute().parent;PARENT=H.parent
REF=PARENT/'IEEE8500_B0_POLICY_SCALE058_20260915';BG=PARENT/'IEEE8500_B0_BG_SCALE_20260915'
sys.dont_write_bytecode=True;sys.path.insert(0,str(BG/'plot_deps'));os.environ['MPLCONFIGDIR']=str(H/'mpl_config')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def label(a):return f'{a:.6f}'.rstrip('0').rstrip('.')
start=datetime.fromisoformat('2025-05-01T00:00:00+10:00')
stamp=lambda t:(start+timedelta(minutes=15*int(t))).isoformat()
results=read(H/'SCREEN_TABLE.json');selection=read(H/'SEARCH_RESULT.json');selected=selection['selected']
geo=read(REF/'GEOMETRY.json');names=[r['name'].lower() for r in geo['lines']];segments=np.array([r['xy'] for r in geo['lines']])
reference_name=read(REF/'B0_SUMMARY.json')['line_witness'].split('|')[0].lower()
center=segments[names.index(reference_name)].mean(axis=0)
bounds=[segments[:,:,0].min(),segments[:,:,0].max(),segments[:,:,1].min(),segments[:,:,1].max()]
span=max(bounds[1]-bounds[0],bounds[3]-bounds[2]);zoom=span*.035
extents=dict(whole=[bounds[0]-.025*span,bounds[1]+.025*span,bounds[2]-.025*span,bounds[3]+.025*span],detail=[center[0]-zoom,center[0]+zoom,center[1]-zoom,center[1]+zoom])
norm=Normalize(0,1);cmap=plt.get_cmap('YlOrRd')
def draw(ax,values,local=False):
    order=np.argsort(values);lc=LineCollection(segments[order],cmap=cmap,norm=norm,linewidths=1.1 if local else .9);lc.set_array(values[order]);ax.add_collection(lc)
    b=extents['detail' if local else 'whole'];ax.set_xlim(b[:2]);ax.set_ylim(b[2:]);ax.set_aspect('equal');ax.set_facecolor('#f4f6f8');ax.set_xticks([]);ax.set_yticks([])
    for sp in ax.spines.values():sp.set_visible(False)
    ax.plot(*center,'o',ms=8,mfc='none',mec='#142b45',mew=1)
def plot(values,row,title,path):
    fig,axes=plt.subplots(1,2,figsize=(14,7),layout='constrained',gridspec_kw={'width_ratios':[1.7,1]})
    for k,ax in enumerate(axes):draw(ax,values,bool(k));ax.set_title('Critical-line area (original coordinates)' if k else 'Whole feeder (original coordinates)',fontsize=11)
    fig.colorbar(ScalarMappable(norm,cmap),ax=axes,shrink=.8,label='Line loading [pu] | common scale 0 to 1')
    fig.suptitle(f'IEEE8500 B0 policy | background {label(row["scale"])} | AIDC reference ON | MESS OFF\n'+title,fontsize=14)
    fig.supxlabel(f'Peak {row["max_line_loading"]:.6f} pu | Vmin {row["Vmin"]:.6f} pu | AC {row["status"]} | fixed PV alpha 0.50',fontsize=11)
    fig.savefig(path,dpi=180);plt.close(fig)
peaks=[];plot_files=[]
for row in results:
    folder=Path(row['folder']);out=H/('scale_'+label(row['scale']));out.mkdir(exist_ok=True)
    assert read(folder/'GEOMETRY.json')==geo
    with np.load(folder/'B0_ALL_PHASE_ARRAYS.npz') as z:
        a=z['line_current_loading_pu'];labels=z['line_phase_axes'];byline={}
        for j,x in enumerate(labels):byline.setdefault(str(x).split('|')[0].lower(),[]).append(j)
        assert set(byline)==set(names) and np.isfinite(a).all()
        peak=np.array([a[:,byline[n]].max() for n in names]);peaks.append(peak)
        assert peak.max()==row['max_line_loading']
        path=out/'B0_DAILY_MAX_HEATMAP.png';plot(peak,row,'Daily maximum across 96 slots, terminals and local phases | 2025-05-01',path);plot_files.append(path)
        if row['scale']==selected['scale']:
            at=np.array([a[row['critical_slot'],byline[n]].max() for n in names]);assert at.max()==peak.max()
            plot(at,row,f'System critical time: slot {row["critical_slot"]}, {stamp(row["critical_slot"])}',out/'B0_CRITICAL_TIME_HEATMAP.png')
            plot_files.append(out/'B0_CRITICAL_TIME_HEATMAP.png')
cols=4;nrows=(len(results)+cols-1)//cols
fig,axes=plt.subplots(nrows,cols,figsize=(18,5*nrows),layout='constrained');flat=np.asarray(axes).ravel()
for ax,row,peak in zip(flat,results,peaks):
    draw(ax,peak);ax.set_title(f'{label(row["scale"])} | {row["status"]}\nVmin {row["Vmin"]:.6f} | peak {row["max_line_loading"]:.6f}',fontsize=11)
for ax in flat[len(results):]:ax.axis('off')
fig.colorbar(ScalarMappable(norm,cmap),ax=flat.tolist(),shrink=.7,label='Common loading [pu]')
fig.suptitle('IEEE8500 actual B0 policy | fine background-scale search | original geometry',fontsize=17)
fig.savefig(H/'ALL_CANDIDATE_DAILY_MAX_HEATMAPS.png',dpi=150);plt.close(fig)

# Final recommended CSV schema exactly matches the preceding B0-policy .58 CSV schema.
folder=Path(selected['folder']);z=np.load(folder/'B0_ALL_PHASE_ARRAYS.npz');a=z['line_current_loading_pu'];labels=z['line_phase_axes'];slot=selected['critical_slot']
byline={};parsed=[]
for j,x in enumerate(labels):
    name,term,bus,node=str(x).split('|');name=name.lower();byline.setdefault(name,[]).append(j);parsed.append((name,int(term[1:]),int(node[4:])))
metadata=list(csv.DictReader((REF/'heatmap_csv/IEEE8500_B0_POLICY_SCALE058_DAILY_MAX_HEATMAP.csv').open(encoding='utf-8')))
daily=[];critical=[];basecols='element_type element_id from_bus to_bus x_from y_from x_to y_to'.split()
for old in metadata:
    r={k:old[k] for k in basecols}
    for k in ['x_from','y_from','x_to','y_to']:r[k]=float(r[k])
    for b,x,y in [('from_bus','x_from','y_from'),('to_bus','x_to','y_to')]:assert [r[x],r[y]]==geo['coordinates'][r[b]]
    idx=byline.get(r['element_id'],[])
    if not idx:
        assert old['data_status']=='DISABLED'
        daily.append(dict(**r,data_status='DISABLED',B0_element_max_loading=None,max_terminal=None,max_phase=None,max_slot=None,max_time_AEST=None))
        critical.append(dict(**r,terminal=None,phase=None,data_status='DISABLED',B0_loading_at_critical_time=None,critical_slot=slot,critical_time_AEST=stamp(slot)));continue
    values=a[:,idx];t,k=np.unravel_index(values.argmax(),values.shape);w=parsed[idx[int(k)]]
    daily.append(dict(**r,data_status='OK',B0_element_max_loading=float(values[t,k]),max_terminal=w[1],max_phase=w[2],max_slot=int(t),max_time_AEST=stamp(t)))
    for j in idx:
        w=parsed[j];critical.append(dict(**r,terminal=w[1],phase=w[2],data_status='OK',B0_loading_at_critical_time=float(a[slot,j]),critical_slot=slot,critical_time_AEST=stamp(slot)))
brief=dict(background_scale=selected['scale'],critical_slot=slot,critical_time_AEST=stamp(slot),critical_line=selected['critical_line'].lower(),critical_terminal=selected['critical_terminal'],critical_phase=selected['critical_phase'],rho_max=selected['max_line_loading'],Vmin=selected['Vmin'],Vmax=selected['Vmax'],transformer_current_max=selected['transformer_current'],transformer_kVA_max=selected['transformer_kVA'],AC_status=selected['status'],AIDC='B0_REFERENCE_ON',MESS='OFF')
tables=[]
for suffix,data in [('DAILY_MAX_HEATMAP',daily),('CRITICAL_TIME_HEATMAP',critical),('HEATMAP_SUMMARY',[brief])]:
    existing=list(csv.reader((REF/f'heatmap_csv/IEEE8500_B0_POLICY_SCALE058_{suffix}.csv').open(encoding='utf-8')))[0]
    assert list(data[0])==existing
    tables.append(dict(filename=f'B0_{label(selected["scale"])}_{suffix}.csv',columns=existing,rows=[[r[c] for c in existing] for r in data]))
# Search CSV includes all witness and convergence fields, not just rounded display metrics.
tables.append(dict(filename='FINE_SCREEN_TABLE.csv',columns=list(results[0]),rows=[[r[c] for c in results[0]] for r in results]))
out=H/'csv';out.mkdir(exist_ok=True);(out/'extracted_tables.json').write_text(json.dumps(tables,allow_nan=False),encoding='utf-8')
shutil.copyfile(REF/'heatmap_csv/export.mjs',out/'export.mjs')
report=['# IEEE8500 B0 fine background-scale feasibility search','',f'**Production recommendation: {label(selected["scale"])}.** B0 reference AIDC ON, MESS OFF; May01 D-1 demand/PV, PV alpha 0.50 and all spatial/control/rating settings preserved.','',
'| scale | Vmin | Vmax | max line loading | transformer current | transformer kVA | AC | Vmin >= 0.9505 |','|---:|---:|---:|---:|---:|---:|:---:|:---:|']
for r in results:report.append(f'| {label(r["scale"])} | {r["Vmin"]:.9f} | {r["Vmax"]:.9f} | {r["max_line_loading"]:.9f} | {r["transformer_current"]:.9f} | {r["transformer_kVA"]:.9f} | {r["status"]} | {"YES" if r["production_margin_ok"] else "NO"} |')
report+=['','```ini']
for k in ['MAX_FEASIBLE_TESTED_SCALE','FIRST_INFEASIBLE_TESTED_SCALE','RECOMMENDED_PRODUCTION_SCALE','RECOMMENDED_B0_PEAK_LOADING','RECOMMENDED_VMIN_MARGIN']:report.append(f'{k} = {selection[k]:.12f}')
report+=['```','',f'Final tested feasibility bracket: [{selection["boundary_lower"]}, {selection["boundary_upper"]}], width {selection["boundary_width"]}. This is a tested bracket, not a continuous mathematical maximum. Native discrete controls can be nonmonotone. Observed FAIL-to-PASS reversals: {selection["observed_feasibility_reversals"]}.','',
'Hard limits remain Vmin >= 0.95, Vmax <= 1.05, line/current/kVA <= 1.0 pu. The 0.9505 criterion is used only to recommend production margin, not to change hard PASS/FAIL. Recommendation chooses the greatest exact peak line loading among tested candidates meeting that margin.',
'','## Boundary refinement','']
for r in read(H/'SEARCH_TRACE.json'):report.append(f'- [{r["lower_before"]}, {r["upper_before"]}] -> midpoint {r["midpoint"]}: {r["status"]}')
report+=['','## Witnesses','', '| Scale | Vmin node / slot | Peak line / terminal / local phase / slot |','|---:|---|---|']
for r in results:report.append(f'| {label(r["scale"])} | {r["Vmin_node"]} / {r["Vmin_slot"]} | {r["critical_line"]} / {r["critical_terminal"]} / {r["critical_phase"]} / {r["critical_slot"]} |')
report+=['',f'Recommended critical time: {stamp(slot)} (0-based slot start, AEST). Forecast interval-end timestamp is 15 minutes later. Local phase is the raw OpenDSS node number; a triplex node 1 is not an inferred primary A phase.','',
'## Preserved inputs and validation','',f'- New independent contexts: {selection["new_fresh_contexts"]}, each with 96 sequential exact AC snapshots. Existing .580 reference reused with hashes verified. All candidates have 96/96 convergence and settled controls.','- source=1.04 pu; Vreg=123.5 V; CAPBank3 OFF; all other native controls unchanged. Native P/Q are multiplied by the background scalar uniformly.','- B0 workload/PCC P/Q are replayed unchanged; MESS P/Q remain zero. PV spatial allocation, alpha=.50 and temporal profile are fixed.','- Topology, bus/phase distribution, host/PCC locations, line/transformer ratings, coordinates and prior authorities are unchanged. Static/spatial hashes match the existing .58 run.','- B1/B2/B3 and scheduling optimization calls: 0. Authority promotion: none.','',
'## Heatmaps and CSV','', '- Every tested candidate has `scale_<value>/B0_DAILY_MAX_HEATMAP.png`, including a newly rendered map of reused .580 raw results.','- Recommended scale also has `B0_CRITICAL_TIME_HEATMAP.png`.','- All maps use YlOrRd, 0–1 pu, the original .58 whole-feeder extent and original .58 detail viewport. No reflection, rotation, translation or scaling of coordinates.','- Daily map: maximum per physical line across all 96 slots and terminals/phases. Critical map: same system-critical slot for all lines, maximum terminal/phase per line.','- Final CSV schemas exactly match the preceding actual-B0 .58 CSV. All loading values are pu. Daily 3,703 rows; critical 12,317 rows; summary 1 row. Five disabled lines have empty loading and DISABLED status; all monitored values are finite.','- Critical CSV is terminal/phase-grained. Group by element_id and take max(B0_loading_at_critical_time) for one color per physical line.','', '## Candidate images','']
for r in results:report.append(f'- [{label(r["scale"])} daily max](scale_{label(r["scale"])}/B0_DAILY_MAX_HEATMAP.png)')
(H/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
(H/'HEATMAP_VALIDATION.json').write_text(json.dumps(dict(status='PASS',same_original_coordinates=True,same_reference_extents=extents,colormap='YlOrRd',colorbar=[0,1],all_candidate_daily_maxima_match_raw=True,selected_critical_max_matches_raw=True,daily_rows=len(daily),critical_rows=len(critical),schema_matches_previous_policy=True,files=[str(p) for p in plot_files]),indent=2),encoding='utf-8')
print('RENDER_AND_TABLES_COMPLETE',json.dumps(brief),flush=True)
