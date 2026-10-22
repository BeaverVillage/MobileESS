"""Current A2 -> M2 affine anchor, with newly generated static proofs.

The original r043 M constructor uses the dated frozen Planning response for
both M1 and M2, substituting the accepted AIDC controls. This adapter follows
that contract: Jacobians/state trajectory remain frozen, every affected RHS
is rebound to the current C1 P/Q and every bound/removal proof is regenerated.
The preparation fixture is never an accepted A2 or optimized M1 result.
"""
from dataclasses import asdict
import os,types,sys
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .static_common import RUNTIME,HIST_RUN
from .static_pack import PACK as ORIGINAL,N_AUX
from .stage_a_grid import component
from .stage_aidc import power_bounds

MROOT=WORK/'M2';MPACK=MROOT/'SOURCE_YY_FULL96';MDOC=OUT/'stage_m2'

def fixed_a2_fixture():
    from .prestart_acceptance import source_domain,certify
    from v42_job_capability import Option
    from v43_arms.reference import project
    day=day_inputs();bundle=read(day['files']['native']['path']);windows=read(day['files']['windows']['path'])
    jobs,bounds,seconds,r,raw=source_domain(bundle,windows)
    chosen={u:asdict(Option(j.reference_start,j.reference_site,((j.reference_site,j.reference_start,j.reference_start+j.service_slots),))) for u,j in jobs.items()}
    selected=read(ROOT/'docs/v2_add/integration/AIDC_SAME_POLICY_STUDY.json')['selected']
    chosen.update(selected);cert=certify(chosen,bundle,windows,identity={},expected_identity={});assert cert['PASS']
    sites,caps,known,anon,*_=project(bundle);known=known.copy()
    for u,o in selected.items():
        j=jobs[u]
        for site,start,end,sign in [(j.reference_site,j.reference_start,j.reference_start+j.service_slots,-1)]+[(s,a,b,1) for s,a,b in o['segments']]:
            for t in range(max(0,start-24),min(96,end-24)):known[t,sites.index(site)]+=sign*j.gpu
    assert np.min(known)>=0 and np.max(known+anon-caps)<=1e-8
    bounds,power_pack=power_bounds(bundle);_,power,idle,swing=power_pack
    p=np.array([[power[s,t].slope*(idle*caps[j]+swing*(known[t,j]+anon[t,j]))+power[s,t].intercept_kw for j,s in enumerate(sites)] for t in range(96)])
    identity=dict(day=day['day'],stage='A2',scope='FINITE_ORIGINAL_FULL_JOB_FIXTURE_NOT_OPTIMIZED_OR_ACCEPTED_A2',
        input=day['files']['native'],windows=day['files']['windows'],selected_sha=digest(chosen),
        C1_P_sha=digest(p.tolist()),PF=.95,selected_change=selected,full_Job_acceptance=cert)
    return p,identity

def prepare():
    with measured('M2_CURRENT_ANCHOR_REBINDING.json') as (report,start):
        MROOT.mkdir(exist_ok=True);MPACK.mkdir(exist_ok=True);MDOC.mkdir(exist_ok=True)
        p,identity=fixed_a2_fixture();np.save(MROOT/'A2_P.npy',p)
        (MROOT/'A2_FIXTURE.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2),encoding='utf-8')
        from shutil import copyfile
        for name in ('MOBILITY.npz','MOBILITY_DOMAIN.npz','MOBILITY_POINT.npy','OBJECTIVES.json','MOBILITY_RECEIPT.json'):
            if not (MPACK/name).exists():os.link(ORIGINAL/name,MPACK/name)
            assert record(MPACK/name)['sha256']==record(ORIGINAL/name)['sha256']
        bounds,_=power_bounds(read(day_inputs()['files']['native']['path']));records=[]
        for t in range(96):
            guard(start);folder=MPACK/f'{t:02d}';folder.mkdir(exist_ok=True)
            for name in ('MATRIX.npz','DOMAIN.npz'):
                if not (folder/name).exists():os.link(ORIGINAL/f'{t:02d}'/name,folder/name)
            A,d,eq,H,c,proof=component(t,bounds[t],np.zeros(48))
            with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:delta=p[t]-z['anchor'][:12]
            with np.load(ORIGINAL/f'{t:02d}/ROWS.npz') as z:r={k:z[k] for k in z.files}
            rhs=r['rhs'].copy();rhs[48:]-=A[:,:12]@delta
            np.savez_compressed(folder/'ROWS.npz',**dict(r,rhs=rhs))
            rr=dict(slot=t,original_matrix_unchanged=True,current_fixed_AIDC_P=p[t].tolist(),delta_from_B0_P=delta.tolist(),
                RHS_max_change=float(abs(rhs-r['rhs']).max()),rows=record(folder/'ROWS.npz'),coefficient=proof['source_coefficient'])
            (folder/'RECEIPT.json').write_text(json.dumps(rr),encoding='utf-8');records.append(rr)
            if t%12==0:print('M2 NEW CURRENT A2 ANCHOR',t,flush=True)
        reference=dict(PASS=True,stage='M2',fixture=True,A2=identity,records=records,old_B0_screen_reused=False,
            Jacobian_policy='Original dated frozen Planning response; accepted AIDC controls substituted, not a new AC relinearization')
        reference['case_sha']=digest(reference)
        (MDOC/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json').write_text(json.dumps(reference,indent=2),encoding='utf-8')
        # Mobility static presolve is independent of AIDC/grid constants. Reuse
        # its exact source transport, not any old grid removal mask.
        (MROOT/'mobility').mkdir(exist_ok=True)
        for source in (RUN/'mobility').iterdir():
            if source.is_file() and not (MROOT/'mobility'/source.name).exists():os.link(source,MROOT/'mobility'/source.name)
        copyfile(OUT/'ORIGINAL_STATIC_PRESOLVE_MESS8.json',MDOC/'ORIGINAL_STATIC_PRESOLVE_MESS8.json')
        report.update(PASS=True,current_A2_fixture=identity,current_case_sha=reference['case_sha'],records=records,
            M1_grid_proof_reused=False,fixture_not_production_A2=True)

def rebound(module,function='prepare'):
    from . import may01_compact as old
    load=types.FunctionType(old.load.__code__,dict(old.load.__globals__,PACK=MPACK))
    projection=types.FunctionType(old.projection.__code__,dict(old.projection.__globals__,load=load))
    def output(name,value):
        if isinstance(value,dict):value=dict(value,current_stage='M2',scope='Current finite FULL A2 anchor; not an official optimized/accepted A2 result')
        p=MDOC/name;p.write_text(json.dumps(value,default=str,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');return value
    def table(name,rows):
        import csv
        rows=list(rows)
        with (MDOC/name).open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));writer.writeheader();writer.writerows(rows)
    fn=getattr(module,function);ns=dict(fn.__globals__,RUN=MROOT,OUT=MDOC,PACK=MPACK,CACHE=MROOT/'screen',
        load=load,projection=projection,put=output,table=table,init=lambda:resources(),guard=guard)
    result=types.FunctionType(fn.__code__,ns,argdefs=fn.__defaults__);result.__kwdefaults__=fn.__kwdefaults__
    return result

def screening():
    from . import static_screen,static_verify
    rebound(static_screen)();rebound(static_verify,'verify')()

def native0():
    from . import static_native,static_transport_verify
    with measured('M2_FIXED_A2_STATIC_NATIVE0.json') as (report,start):
        rebound(static_native,'build')()
        result=read(MDOC/'IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json')
        report.update(result,scope='Current finite FULL A2 fixture; production M2 requires actual accepted A2 payload',
            current_A2=record(MROOT/'A2_FIXTURE.json'),M1_static_grid_screen_reused=False)
        if result.get('PASS'):
            rebound(static_transport_verify,'verify')()
            report['independent_transport']=read(MDOC/'NATIVE_ORIGINAL_TRANSPORT_VERIFICATION.json')

if __name__=='__main__':globals()[sys.argv[1]]()
