"""Actual selected Native point -> raw FULL validation, before K48 ranking."""
import pickle,sys
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .static_pack import PACK,N_AUX
from .stage_m_validation import strict,validate
from .prestart_native import native_zero
from v42_native.contracts import digest


def certify(stage='M1'):
    with measured(stage+'_ORIGINAL_FULL_VALIDATOR_BINDING.json') as (report,start),native_zero() as denied:
        root=RUN if stage=='M1' else WORK/'M2';pack=PACK if stage=='M1' else root/'SOURCE_YY_FULL96'
        doc=OUT if stage=='M1' else OUT/'stage_m2'
        assert read(doc/'NATIVE_ORIGINAL_TRANSPORT_VERIFICATION.json')['PASS']
        with (root/'mobility/TRANSPORT.pkl').open('rb') as f:transport=pickle.load(f)
        with np.load(pack/'MOBILITY_DOMAIN.npz') as z:md={k:z[k] for k in z.files}
        mob=sp.load_npz(pack/'MOBILITY.npz');n=mob.shape[1]
        A=sp.load_npz(root/'native/COMPLETE_A.npz')
        with np.load(root/'native/COMPLETE_DOMAIN.npz') as z:d={k:z[k] for k in z.files}
        p=transport['presolve'];maps=[]
        for t in range(96):
            with np.load(root/'native'/f'{t:02d}_MAP.npz') as z:maps.append(z['original_aux_to_native'])
        def lift(point):
            full=np.zeros(n+96*N_AUX);full[:n]=p.inverse(point[:len(p.col_ids)])[:n]
            for t,mp in enumerate(maps):
                C=sp.load_npz(root/'screen'/f'{t:02d}/RECONSTRUCTION.npz');a=np.load(root/'screen'/f'{t:02d}/CONSTANT.npy')
                grid=np.r_[point[mp[:48]],a+C@point[mp[:48]]];keep=mp>=0;grid[keep]=point[mp[keep]]
                full[n+t*N_AUX:n+(t+1)*N_AUX]=grid
            return full
        fulltypes=np.r_[md['types'],np.full(96*N_AUX,'C')]
        identity=dict(stage=stage,selected=record(root/'native/COMPLETE_A.npz'),
            domain=record(root/'native/COMPLETE_DOMAIN.npz'),reference=record(doc/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json'))
        case=SimpleNamespace(A=A,d=d,raw_pack=pack,graph=transport['graph'],lift=lift,
            _blocks=SimpleNamespace(nbase=n,mob=mob,md=md),original_d=dict(types=fulltypes),case_sha=digest(identity))
        results=[]
        for name in ('STAY','MULTI_MOVE_PQ_REBOUND'):
            raw=np.load(root/(name+'_SOURCE_YY_FULL_POINT.npy'))
            compact=transport['compact'].forward(raw[:n])
            point=np.zeros(A.shape[1]);point[:len(p.col_ids)]=p.forward(compact)
            for t,mp in enumerate(maps):
                keep=mp>=0;point[mp[keep]]=raw[n+t*N_AUX:n+(t+1)*N_AUX][keep]
            folder=WORK/(stage+'_VALIDATOR_FIXTURE');folder.mkdir(exist_ok=True)
            path=folder/(name+'.npz');np.savez_compressed(path,point=point)
            certificate=strict(case,path);assert certificate['PASS']
            results.append(dict(witness=name,point=record(path),certificate=certificate))
            print('ORIGINAL FULL VALIDATOR',stage,name,flush=True)
        changed=point.copy()
        native_helper=next(int(mp[k]) for mp in maps for k in range(48,len(mp)) if mp[k]>=0)
        changed[native_helper]+=.125
        bad=validate(case,changed);assert not bad['PASS']
        report.update(PASS=True,results=results,retained_helper_tampering_rejected=True,
            raw_Native_retained_helpers_not_repaired=True,denied_attempts=denied,
            scope='Real complete selected Native coordinates and current original FULL validator; no numerical optimization or K48 bound claimed',
            original_validator=record(ROOT/'v42_m1_research/check_ub.py'))


if __name__=='__main__':certify(sys.argv[1] if len(sys.argv)>1 else 'M1')
