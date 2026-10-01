"""Zero-optimize F3 identity/template and independently aligned root duals."""
from .common import *
import gurobipy as gp

def run():
    b=base();from v42_relaxation.strengthening import hook
    cert=read(RELAX/'S3_BARRIER_OPTIMALITY_CERTIFICATE.json');saved=read(RELAX/'S3_ROOT_LP_OPTIMIZATION.json')
    chosen='S3' if cert['PASS'] and cert['BarStatus']==2 and cert['width']<=OBJ_TOL and saved['matrix_validation']['PASS'] else 'S2'
    def inspect_root(m,obj,*args):
        m.setObjective(obj[0][1]);m.update()
        with np.load(RELAX/(chosen+'_ROOT_LP_SOLUTION.npz'),allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
        matrix=b.matrix_validate(m,v)
        if chosen=='S3':
            with np.load(RELAX/'S3_BARRIER_DUAL.npz',allow_pickle=False) as z:pi=z['BarPi']
        else:
            # Use inherited S2 dual only if present; never fabricate unavailable duals.
            path=RELAX/'S2_ROOT_LP_DUAL.npz';assert path.exists(),'S2_DUAL_UNAVAILABLE_STOP_FOR_SOURCE_INTEGRITY'
            with np.load(path,allow_pickle=False) as z:pi=z['Pi']
        names=np.asarray(m.getAttr('ConstrName'));assert len(pi)==len(names) and np.isfinite(pi).all()
        np.savez_compressed(OUT/'ROOT_DUAL_AXIS.npz',names=names,Pi=pi)
        dump('ROOT_SOURCE_RECEIPT.json',dict(PASS=True,selected=chosen,rho=v['rho_max'],certificate=cert,full_matrix_revalidation=matrix,
            solution_sha256=sha(RELAX/(chosen+'_ROOT_LP_SOLUTION.npz')),dual_count=len(pi),dual_finite=True,optimize_calls=0,
            overall_status=11 if chosen=='S3' else 2,barrier_status=2 if chosen=='S3' else None,not_relabelled_overall_optimal=True))
        return None,dict(optimize_calls=0)
    b.build(inspect_root,hook(chosen,compact_energy_bounds=chosen=='S3'))
    def inspect_f3(m,obj,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        m.setObjective(obj[0][1]);m.update();v=data[2]['values'].copy();map_bindings(bindings,v)
        m.setAttr('Start',[v[n] for n in m.getAttr('VarName')]);m.update();identity=b.stats(m);assert identity==b.EXPECTED
        matrix=b.matrix_validate(m,v);dump('BASE_F3_IDENTITY.json',dict(PASS=True,observed=identity,expected=b.EXPECTED,retained_integer_matrix=matrix,optimize_calls=0))
        assert not (LOCAL/'F3.mps').exists();m.write(str(LOCAL/'F3.mps'))
        names=np.asarray(m.getAttr('VarName'));rownames=np.asarray(m.getAttr('ConstrName'))
        np.savez_compressed(OUT/'F3_MODEL_AXIS.npz',names=names,original_types=np.asarray(m.getAttr('VType')),lower=np.asarray(m.getAttr('LB')),upper=np.asarray(m.getAttr('UB')),
            start=np.asarray([v[n] for n in names]),terminal_rows=np.flatnonzero(rownames=='terminal_SOC'),rownames=rownames)
        dump('F3_TEMPLATE_RECEIPT.json',dict(PASS=True,sha256=sha(LOCAL/'F3.mps'),identity=identity,native_source_sha256=sha(ROOT/'v42_native/mess.py'),grid_source_sha256=sha(ROOT/'v42_m1_sparse/grid.py'),optimize_calls=0))
        return None,dict(optimize_calls=0)
    b.build(inspect_f3)
    print('SOURCE & EXACT F3 TEMPLATE PASS',chosen,flush=True)
if __name__=='__main__':run()
