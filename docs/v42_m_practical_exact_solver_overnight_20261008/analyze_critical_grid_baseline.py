"""Current incumbent's original C3A rho-defining grid rows; solve=0."""
from practical_support import *
def run():
    A,d,_=hc.load();source=OUT/'runs/native_production_initial/BEST_VALID_POINT.npz'
    with np.load(source) as z:x=z['x'].copy()
    rho=int(np.flatnonzero(d['objective'])[0]);coef=np.asarray(A[:,rho].toarray()).ravel();lhs=np.asarray(A@x).ravel()
    lower=((coef<0)&(d['sense']=='<'))|((coef>0)&(d['sense']=='>'));indices=np.flatnonzero(lower)
    rows=[]
    for i in indices:
        required=float((d['rhs'][i]-(lhs[i]-coef[i]*x[rho]))/coef[i])
        rows.append(dict(row=int(i),name=str(d['row_names'][i]),required_rho=required,incumbent_rho=float(x[rho]),slack_in_rho=float(x[rho]-required),rho_coefficient=float(coef[i])))
    rows.sort(key=lambda r:(-r['required_rho'],r['row']));table(OUT/'CRITICAL_GRID_BASELINE.csv',rows[:200])
    atomic(OUT/'CRITICAL_GRID_BASELINE.json',dict(UTC=stamp(),optimize_calls=0,source_SHA256=sha(source),rho_defining_rows=len(rows),top=rows[:10],all_original_rows_and_objective_unchanged=True,diagnostic_ratios_not_new_bounds=True,full_original_physical_grid_replay=read(OUT/'runs/native_production_initial/INDEPENDENT_AUDIT.json')['PASS']))
    print(json.dumps(dict(rho_defining_rows=len(rows),top=rows[:5])))
if __name__=='__main__':run()
