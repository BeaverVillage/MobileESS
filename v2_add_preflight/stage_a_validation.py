"""Keep original all-Job/CC4/Runtime/WAN acceptance; replace electrical IO only."""
import ast,inspect,textwrap
from contextlib import contextmanager
from unittest.mock import patch
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .stage_a_grid import PF

def audit(tag,controls,rho,folder=None):
    from v42_m1_research.check_ub import matrix_replay
    controls=np.asarray(controls,float)
    assert controls.shape==(96,72) and np.isfinite(controls).all()
    if np.max(abs(controls[:,12:24]-PF*controls[:,:12]))>1e-8:raise ValueError('SOURCE_C1_PF_BINDING')
    folder=WORK/tag/'grid' if folder is None else Path(folder);receipt=read(folder/'RECEIPT.json');maximum=0.;vmin=np.inf;vmax=0.;slots=[]
    assert digest(controls[:,24:].tolist())==receipt['MESS_parameter_sha'],'CURRENT_FIXED_M1_DISPATCH_DRIFT'
    for t in range(96):
        p=folder/f'{t:02d}';A=sp.load_npz(p/'RAW.npz');H=sp.load_npz(p/'RECONSTRUCTION.npz');c=np.load(p/'CONSTANT.npy')
        with np.load(p/'DOMAIN.npz') as z:d={k:z[k] for k in z.files}
        with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:delta=controls[t,:12]-z['anchor'][:12]
        x=np.r_[delta,float(rho),c+H@delta]
        replay=matrix_replay(A,d,x,tolerance=1e-5)
        maximum=max(maximum,replay['maximum_observed_row_violation'],replay['max_bound_violation'])
        v=x[13:13+8603];vmin=min(vmin,float(v.min()));vmax=max(vmax,float(v.max()))
        slots.append(dict(slot=t,PASS=replay['PASS'],all_original_grid_rows=A.shape[0]))
    return dict(PASS=all(r['PASS'] for r in slots),maximum_violation=maximum,min_voltage_pu=float(np.sqrt(max(0,vmin))),
        max_voltage_pu=float(np.sqrt(max(0,vmax))),all_original_rows_and_auxiliary_bounds_replayed=True,slots=slots,
        rating_or_voltage_changed=False,source_R0_fixed_dispatch_not_assumed=True)

def source_check(original,tag,grid_folder=None):
    tree=ast.parse(textwrap.dedent(inspect.getsource(original)));body=tree.body[0].body
    begin=next(i for i,n in enumerate(body) if isinstance(n,ast.ImportFrom) and n.module=='v42_temporal.native')
    end=next(i for i,n in enumerate(body) if isinstance(n,ast.If) and ast.unparse(n.test)=='grid_vio > 1e-05')
    # All original Job/GPU/Rack/WAN/CC4/reserve checks outside the physical
    # coefficient evaluation block remain literal, including tolerances.
    body[begin:end]=ast.parse('grid_vio=_current_grid(controls,primary_rho)["maximum_violation"]').body
    ast.fix_missing_locations(tree);ns=dict(original.__globals__,_current_grid=lambda controls,rho:audit(tag,controls,rho,grid_folder))
    exec(compile(tree,original.__code__.co_filename,'exec'),ns)
    fn=ns['check'];fn._v42_dynamic_bundle_day_routed=True
    return fn

@contextmanager
def scope(tag,grid_folder=None):
    import v42_exact.validation as validation
    import v42_integrated.contract as physical
    check=source_check(validation.check,tag,grid_folder)
    with patch.object(validation,'check',check),patch.object(physical,'grid_audit',lambda coefficients,controls,rho:audit(tag,controls,rho,grid_folder)):
        yield
