"""Original FULL validator, streamed over actual raw reference components.

The original sparse enclosure/Fraction checks and original physical replay are
called unchanged. All retained auxiliary coordinates are copied verbatim;
only variables proven eliminated by equality are reconstructed.
"""
from fractions import Fraction as F
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .static_pack import N_AUX

def validate(case,point):
    from v42_m1_research.check_ub import matrix_replay,physical_replay,vector_sha
    start=time.perf_counter();point=np.asarray(point);before=vector_sha(point)
    if point.dtype!=np.float64 or point.shape!=(case.A.shape[1],) or not np.isfinite(point).all():raise ValueError('LITERAL_CURRENT_RAW_POINT_REQUIRED')
    selected=matrix_replay(case.A,case.d,point)
    assert selected['checked_binary_columns']==int(np.sum(case.d['types']=='B'))
    full=case.lift(point);b=case._blocks;n=b.nbase
    original=matrix_replay(b.mob,b.md,full[:n])
    physics=physical_replay(SimpleNamespace(graph=case.graph,original_d=b.md),full[:n]);results=[]
    for t in range(96):
        guard(start);A=sp.load_npz(case.raw_pack/f'{t:02d}/MATRIX.npz');lo=n+t*N_AUX
        with np.load(case.raw_pack/f'{t:02d}/DOMAIN.npz') as z:vd={k:z[k] for k in z.files}
        with np.load(case.raw_pack/f'{t:02d}/ROWS.npz') as z:r={k:z[k] for k in z.files}
        cols=np.unique(A.indices);local=A[:,cols]
        d=dict(rhs=r['rhs'],sense=r['sense'],lower=np.full(len(cols),-np.inf),upper=np.full(len(cols),np.inf),
            types=np.full(len(cols),'C'),objective=np.zeros(len(cols)),constant=0.)
        where=np.searchsorted(cols,np.arange(lo,lo+N_AUX));present=(where<len(cols))
        present[present]&=cols[where[present]]==np.arange(lo,lo+N_AUX)[present]
        for key in ('lower','upper','types'):d[key][where[present]]=vd[key][present]
        replay=matrix_replay(local,d,full[cols],tolerance=1e-6,row_tolerances=np.where(r['sense']=='=',1e-6,1e-8))
        results.append(dict(slot=t,**replay))
    exact=F(float(case.d['constant']))+sum((F(float(w))*F(float(point[j])) for j,w in enumerate(case.d['objective']) if w),F(0))
    rho=np.flatnonzero(b.md['objective']);assert len(rho)==1
    assert exact==F(float(full[int(rho[0])])) and before==vector_sha(point)
    passed=selected['PASS'] and original['PASS'] and physics['PASS'] and all(r['PASS'] for r in results)
    return dict(PASS=bool(passed),case_sha=case.case_sha,point_sha256=before,objective=float(exact),exact_objective=str(exact),
        selected_static=selected,original_mobility=original,physical=physics,original_grid96=results,
        every_original_row_and_domain_replayed=True,all_retained_Native_values_unchanged=True,
        raw_point_unchanged=True,repairs=0,rounding=0,clipping=0,Native_optimize_calls=0)

def strict(case,path,evidence=None):
    from v42_m1_research.check_ub import vector_sha
    with np.load(path) as z:
        assert z.files==['point'];point=z['point']
    for domain,values in ((case.d,point),(case.original_d,case.lift(point))):
        discrete=values[domain['types']!='C'];binary=values[domain['types']=='B']
        if not np.array_equal(discrete,np.rint(discrete)) or not np.isin(binary,[0.,1.]).all():raise ValueError('LITERAL_INTEGER_PATTERN_REQUIRED')
    replay=validate(case,point)
    if not replay['PASS']:raise ValueError('CURRENT_ORIGINAL_FULL_REPLAY_REJECTED')
    exact=F(replay['exact_objective']);display=float(exact)
    if F(display)<exact:display=float(np.nextafter(display,np.inf))
    return dict(PASS=True,exact_Global_UB=str(exact),Global_UB=display,point_path=str(Path(path).resolve()),
        point_file_sha256=record(path)['sha256'],point_vector_sha256=vector_sha(point),
        strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=replay,Native_optimize_calls=0)
