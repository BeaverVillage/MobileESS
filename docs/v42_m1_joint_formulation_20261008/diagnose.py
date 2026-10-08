"""Select a four-slot fleet/grid window from immutable original ROOT evidence."""
from common import *
from collections import Counter,defaultdict
def run():
    A,d,_=load();x,pi=root_point();objective=objective_identity(A,d);meta=[info(n) for n in d['names']]
    family=np.array([r[0] for r in meta]);slots=np.array([-1 if r[2] is None else r[2] for r in meta]);units=np.array([r[1] or '' for r in meta])
    slack=d['rhs']-A@x;grid=np.flatnonzero(np.isin(d['row_names'],['line_thermal_face','voltage_upper','voltage_lower','transformer_kVA']))
    row_slots={};grid_by_slot=defaultdict(list)
    for i in grid:
        cols=A.indices[A.indptr[i]:A.indptr[i+1]];ts=set(slots[cols]);ts.discard(-1)
        if len(ts)==1:
            t=ts.pop();row_slots[int(i)]=int(t);grid_by_slot[t].append(int(i))
    scores=[]
    # Grid dual activity plus fractionality; deterministic tie breaking.
    for start in range(1,92):
        end=start+4;mask=(slots>=start)&(slots<end)&(family=='node_activity')
        fractionality=float(np.minimum(abs(x[mask]),abs(1-x[mask])).sum())
        rows=[i for t in range(start,end) for i in grid_by_slot[t]]
        support=float(abs(pi[rows]).sum());tight=sum(abs(slack[i])<=1e-6 for i in rows)
        scores.append(dict(start=start,end_exclusive=end,fractionality=fractionality,grid_dual_support=support,tight_grid_rows=tight,near_69_84=69<=start and end<=85,score=support*fractionality))
    nearby=[r for r in scores if r['near_69_84'] and r['fractionality']>0 and r['grid_dual_support']>0]
    chosen=max(nearby or scores,key=lambda r:(r['score'],r['tight_grid_rows'],-r['start']))
    start,end=chosen['start'],chosen['end_exclusive'];unit_scores=[]
    for unit in sorted(set(units)-{''}):
        mask=(units==unit)&(slots>=start)&(slots<end)&(family=='node_activity')
        unit_scores.append((float(np.minimum(abs(x[mask]),abs(1-x[mask])).sum()),unit))
    selected_units=[u for score,u in sorted(unit_scores,key=lambda r:(-r[0],r[1]))[:2]]
    # Choose one common site using ROOT fractional support across both MESS.
    sites=sorted({m[3][1] for m in meta if m[0]=='node_activity' and len(m[3])==3})
    name_to_col={str(n):j for j,n in enumerate(d['names'])};site_scores=[]
    for site in sites:
        cols=[name_to_col.get(f'node_activity[{u},{site},{t}]') for u in selected_units for t in range(start,end)]
        if any(j is None for j in cols):continue
        score=sum(min(abs(float(x[j])),abs(1-float(x[j]))) for j in cols)
        site_scores.append((score,site))
    assert site_scores,'NO_COMPLETE_SITE_COUNT_DISJUNCTION'
    site=max(site_scores,key=lambda r:(r[0],r[1]))[1]
    selected_grid=[]
    for t in range(start,end):
        rows=grid_by_slot[t];rows.sort(key=lambda i:(-abs(float(pi[i])),abs(float(slack[i])),i))
        selected_grid.extend(rows[:2])
        for family_name in ['line_thermal_face','transformer_kVA']:
            candidates=[i for i in rows if d['row_names'][i]==family_name]
            if candidates:selected_grid.append(min(candidates,key=lambda i:(abs(float(slack[i])),i)))
    selected_grid=list(dict.fromkeys(selected_grid))
    target=np.flatnonzero(np.isin(family,['injection_P','injection_Q','Pch','Pdis','Q','SOC']))
    residual=d['objective']-A.T@pi
    census=[]
    for fam in ['injection_P','injection_Q','Pch','Pdis','Q','SOC','response_line_P','response_line_Q','response_line_correction']:
        ids=np.flatnonzero(family==fam);census.append(dict(family=fam,columns=len(ids),max_float_stationarity_residual=float(abs(residual[ids]).max(initial=0)),sum_bound_width_weighted_absolute_residual=float(np.dot(d['upper'][ids]-d['lower'][ids],abs(residual[ids])))))
    report=dict(PASS=True,optimize_calls=0,base_HEAD=BASE,identity=objective,window=chosen,selected_units=selected_units,all_units=sorted(set(units)-{''}),site=site,selected_grid_rows=selected_grid,grid_row_slot_inference='Unique original named-variable slot in each row; generic original row ID retained, no invented physical line label',grid_rows=[dict(row=i,slot=row_slots[i],family=str(d['row_names'][i]),ROOT_slack=float(slack[i]),ROOT_Pi=float(pi[i])) for i in selected_grid],root_source='PR179 original unfixed OPTIMAL barrier LP',root_raw_replay=hc.replay(A,d,x,False),root_objective=float(x[239826]),stationarity_census=census,source_SHA256=dict(A=sha(hc.PARENT/'C3A_A.npz'),DATA=sha(hc.PARENT/'C3A_DATA.npz'),ROOT=sha(ARCHIVE/'external_production/external_nodes/0000/LP_POINT_PROOF.npz')))
    atomic(OUT/'ROOT_WINDOW_SELECTION.json',report);table(OUT/'WINDOW_CENSUS.csv',scores);table(OUT/'DUAL_BLOCK_CENSUS.csv',census)
    print(json.dumps(clean({k:report[k] for k in ['window','selected_units','site','grid_rows']})))
if __name__=='__main__':run()
