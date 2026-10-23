"""Finite original FULL M1 witness for A2 Native0, never production M1."""
import sys
import numpy as np
from .stage_common import *
from .static_pack import PACK,N_AUX
from .stage_a_grid import prepare_grid
from .stage_aidc import power_bounds


def parameter():
    path=RUN/'MULTI_MOVE_PQ_REBOUND_SOURCE_YY_FULL_POINT.npy'
    certificate=read(OUT/'STATIC_FULL_WITNESS_VALIDATION.json')
    witness=certificate['results']['MULTI_MOVE_PQ_REBOUND']
    if witness['PASS'] is not True or witness['physical_replay']['PASS'] is not True:
        raise PermissionError('ORIGINAL_FULL_M1_WITNESS_REQUIRED')
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:n=len(z['lower'])
    full=np.load(path);assert full.shape==(n+96*N_AUX,)
    mess=full[n:].reshape(96,N_AUX)[:,:48].copy()
    assert np.isfinite(mess).all() and np.any(mess!=0.)
    return mess,dict(point=record(path),certificate=record(OUT/'STATIC_FULL_WITNESS_VALIDATION.json'),
        scope='Finite original FULL multi-MOVE/P/Q/SOC M1 witness; not optimized/accepted production M1',
        MESS_parameter_sha=digest(mess.tolist()),full_M1_source_parameter_frozen=True,
        source_sign='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch',time_axis=list(range(96)),
        original_M1_Route_SOC_and_plan_coordinate_file=record(path))


def unit_arrays():
    """Literal per-vehicle witness values; no new route or SOC is synthesized."""
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:names=z['names']
    raw=np.load(RUN/'MULTI_MOVE_PQ_REBOUND_SOURCE_YY_FULL_POINT.npy')
    units=sorted(INITIAL);p=np.zeros((96,8));q=p.copy()
    for j,name in enumerate(names):
        if not str(name).startswith(('Pdis[','Pch[','Q[')):continue
        family,coords=str(name).split('[',1);unit,site,t=coords[:-1].split(',');t=int(t);u=units.index(unit)
        if family=='Q':q[t,u]+=raw[j]
        else:p[t,u]+=raw[j]*(1 if family=='Pdis' else -1)
    control,_=parameter()
    assert np.max(abs(p.sum(axis=1)-control[:,:24].sum(axis=1)))<1e-8
    assert np.max(abs(q.sum(axis=1)-control[:,24:].sum(axis=1)))<1e-8
    return dict(P_kW=p,Q_kvar=q)


def prepare():
    with measured('A2_FIXED_M1_GRID_PREPARATION.json') as (report,start):
        mess,proof=parameter();folder=WORK/'A2';folder.mkdir(exist_ok=True)
        np.save(folder/'FIXED_M1_CONTROLS.npy',mess)
        (folder/'FIXED_M1_WITNESS.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        bundle=read(day_inputs()['files']['native']['path']);bounds,_=power_bounds(bundle)
        result=prepare_grid('A2',bounds,mess)
        from .stage_a_verify import verify
        verify('A2')
        report.update(PASS=True,M1=proof,variable_A2_grid=result,
            independent_grid=record(OUT/'A2_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json'),
            production_requires_original_v44_require_m1=True,accepted_A1_freeze_not_claimed=True)


if __name__=='__main__':prepare()
