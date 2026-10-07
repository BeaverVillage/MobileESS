"""Original binary fractionality vs existing root dual row support; solve=0."""
from practical_support import *
def run():
    A,d,_=hc.load();source=OUT/'external_production/external_nodes/0000/LP_POINT_PROOF.npz'
    with np.load(source) as z:x=z['x'].copy();pi=z['clipped_Pi'].copy()
    binary=np.flatnonzero(d['types']=='B');support=np.asarray(abs(A[:,binary]).T@abs(pi)).ravel();dist=np.minimum(abs(x[binary]),abs(1-x[binary]))
    rows=[]
    for j,v,s,f in zip(binary,x[binary],support,dist):
        rows.append(dict(column=int(j),name=str(d['names'][j]),family=str(d['names'][j]).split('[')[0],value=float(v),fractionality=float(f),dual_row_absolute_support=float(s),objective_coefficient=float(d['objective'][j])))
    table(OUT/'FRACTIONAL_DUAL_SUPPORT.csv',rows)
    chosen=read(source.parent/'RESULT.json')['branch_variable'];row=next(r for r in rows if r['column']==chosen)
    top=sorted([r for r in rows if r['fractionality']>1e-8],key=lambda r:(-r['dual_row_absolute_support'],-r['fractionality'],r['column']))[:20]
    families={family:dict(count=sum(r['family']==family for r in rows),fractional_count=sum(r['family']==family and r['fractionality']>1e-8 for r in rows),nonzero_dual_support_count=sum(r['family']==family and r['dual_row_absolute_support']>0 for r in rows),maximum_dual_row_support=max(r['dual_row_absolute_support'] for r in rows if r['family']==family)) for family in sorted({r['family'] for r in rows})}
    atomic(OUT/'FRACTIONAL_DUAL_SUPPORT.json',dict(UTC=stamp(),optimize_calls=0,source_point_SHA256=sha(source),selected_branch=row,top_material_fractional_columns_by_dual_support=top,families=families,no_branch_rule_changed=True,no_pruning_from_scores=True,interpretation='Absolute dual-weighted row incidence is a heuristic sensitivity indicator; it is not a bound, branch proof or guaranteed objective uplift.'))
    print(json.dumps(dict(selected_branch=row,families=families,top5=top[:5])))
if __name__=='__main__':run()
