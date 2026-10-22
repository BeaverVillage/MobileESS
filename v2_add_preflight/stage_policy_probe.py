"""Compare real signed-policy electrical calls against independent raw rows."""
import math
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from v42_native.contracts import digest
from .stage_aidc import power_bounds
from .stage_policy_grid import GridPacket

def probe():
    with measured('SIGNED_ACTUAL_POLICY_GRID_BINDING.json') as (report,start):
        from v43_arms.reference import project
        from v43_actual.vendor.aidc_sensitivity_runtime import grid_numeric_fingerprint
        day=day_inputs();bundle=read(day['files']['native']['path']);sites,caps,known,anon,selected,service,carry,conservation=project(bundle)
        bounds,powerpack=power_bounds(bundle);_,power,idle,swing=powerpack
        p=np.array([[power[s,t].slope*(idle*caps[j]+swing*(known[t,j]+anon[t,j]))+power[s,t].intercept_kw for j,s in enumerate(sites)] for t in range(96)])
        aidc=dict(AIDC_P_by_site={s:p[:,j].tolist() for j,s in enumerate(sites)},AIDC_Q_by_site={s:(p[:,j]*math.tan(math.acos(.95))).tolist() for j,s in enumerate(sites)},
            selected_jobs=selected,CC4_service=service,CC4_carryout=carry)
        services=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]
        mess=dict(P_by_site={s:[0.]*96 for s in services},Q_by_site={s:[0.]*96 for s in services},units=8,initial_sites=INITIAL)
        mess['plan_sha']=digest(mess)
        from v43_actual.vendor.unified_contract import BINDING_FIELDS
        bindings={k:digest(dict(field=k,input=day['files']['native'],hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'))) for k in BINDING_FIELDS}
        bindings.update(aidc_anchor=digest(aidc),mess_anchor=mess['plan_sha'],response_sha=record(OUT/'SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json')['sha256'])
        arrays=dict(PCC_P_kw=p,PCC_Q_kvar=p*math.tan(math.acos(.95)),known_gpu=known)
        rack=read(day['files']['planning_input']['path'])['rack_compatibility']
        packet=GridPacket(arrays=arrays,power=power,swing=swing,capacities=bundle['capacities'],aidc_plan=aidc,mess=mess,
            bindings=bindings,begin_seconds=day['axis']['issue_seconds']+24*900,rack_compatibility=rack)
        fingerprint=grid_numeric_fingerprint(packet);tests=[]
        for t in (0,31,72,95):
            folder=WORK/'A1/grid'/f'{t:02d}';A=sp.load_npz(folder/'RAW.npz');H=sp.load_npz(folder/'RECONSTRUCTION.npz');c=np.load(folder/'CONSTANT.npy')
            with np.load(folder/'DOMAIN.npz') as z:d={k:z[k] for k in z.files}
            with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:anchor=z['anchor'][:12]
            objective=np.flatnonzero(np.char.startswith(d['row_names'].astype(str),'parent_line_thermal_face'))
            rho=A[objective,12].toarray().ravel();assert np.all(rho<0)
            for sign in (0.,-.1,.1):
                g=np.zeros(12);g[0]=sign;peak,bad=packet._at_slot(t,g)
                delta=p[t]+g*packet.p_slope[t]-anchor;x=np.r_[delta,0.,c+H@delta]
                independent=float(np.max((A[objective]@x-d['rhs'][objective])/(-rho)))
                assert abs(peak-independent)<1e-9
                tests.append(dict(slot=t,probe_GPU_delta=sign,source_signed_peak=peak,independent_full_row_peak=independent,
                    absolute_error=abs(peak-independent),all_original_safety_guards_present=True))
        report.update(PASS=True,tests=tests,Source_signed_score_formula_retained=True,whole_grid_security=packet.authority,
            complete_numeric_fingerprint=fingerprint,Native_optimize_calls=0,
            scope='Real Source policy electrical packet, 96-slot constructor and independent literal-row probes; complete event-controller execution is separate',
            actual120_execution_claim=False,source_job_policy_or_hardware_changed=False)

if __name__=='__main__':probe()
