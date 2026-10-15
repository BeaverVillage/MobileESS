"""Named physical API fixture, never a real Source pre-site authorization."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from v42_integration.release_actual import prepare_packet,prepare_source,RAW,no_native
from v42_integration.current_ac_admission import CurrentACAdmission,CausalObservations
from v42_integration.actual_validation import read,write,record,_validated_hardware_context
from v42_integration.production_case import ARCHIVE
from v42_integration.policy import digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError('NAMED_FIXTURE_MUST_NOT_OVERWRITE')
    files=[Path(__file__),ROOT/'v42_integration/current_ac_admission.py',ROOT/'v42_integration/release_actual.py']
    before=[record(p) for p in files]
    with no_native() as attempts:
        source=prepare_packet(prepare_source());driver=source['arguments'];begin=driver['begin'];sites=tuple(sorted(driver['capacities']))
        obs=CausalObservations.load(RAW,begin=begin,end=begin+1800)
        oracle=CurrentACAdmission(begin=begin,sites=sites,power_model=driver['power_model'],observations=obs,
            source_freeze=source['freeze']['source_freeze'],manifest=read(ARCHIVE/'CAMPAIGN_MANIFEST.json'),mess=source['mess'])
        oracle.observe(begin,[]);public={};base=np.zeros(len(sites))
        for request,site,start in driver['running']:
            public[request.uid]=dict(state='RUNNING',current_site=site,gpu=request.gpu,t50_seconds=request.q50,
                accumulated_compute_seconds=float(request.metadata.get('elapsed_compute_seconds',begin-start)))
            base[sites.index(site)]+=request.gpu
        m=dict(uid='RC01_NAMED_1GPU_Q501800',state='PENDING',origin_unknown=True,gpu=1,t50_seconds=1800)
        rows=[]
        with _validated_hardware_context(oracle.freeze,oracle.manifest):
            for site in ('AIDC01','AIDC12'):
                candidate=base.copy();candidate[sites.index(site)]+=1
                current=oracle.evaluate(begin,candidate,uid=m['uid'])
                prediction=oracle.predicted_score(begin,m,site,public)
                rows.append(dict(site=site,current_candidate=current,conditional_public_Q50_prediction=prediction,
                    capacity_PASS=candidate[sites.index(site)]<=driver['capacities'][site]))
        result=dict(schema='RC01_CONDITIONAL_ORIGINAL_AC_API_FIXTURE_V1',
            evidence_scope='COUNTERFACTUAL_PHYSICAL_API_FIXTURE',
            status='PASS' if all(r['current_candidate']['PASS'] is True and r['capacity_PASS']
                and r['conditional_public_Q50_prediction']['status']=='PASS' for r in rows) else 'NOT_CERTIFIED',
            real_Source_preplacement_permission_granted=False,real_UID_allocated=False,real_PreSite_or_improvement_claim=False,
            private_future_Actual_Runtime_Completion_Weather_Tap_reads=0,
            candidate_public_nominal=m,initial_public_Running=len(public),initial_physical_GPU=float(base.sum()),
            held_exogenous_receipt=obs.at(begin,observed_now=begin),source_files=before,
            Current_and_conditional_prediction_AUTO_states_separate=True,
            conditional_predicted_taps_are_not_Actual_tap_observations=True,physical_source=oracle.manifest,
            original_C1_SHA=driver['power_model'].authority_sha,fixed_MESS_plan_sha=source['mess']['plan_sha'],
            candidate_results=rows,Native_calls=0,Native_attempts=list(attempts))
        if before!=[record(p) for p in files]:raise ValueError('NAMED_FIXTURE_SOURCE_DRIFT')
        result['receipt_sha']=digest(result);write(args.output,result)
        print(result['status'],[(r['site'],r['conditional_public_Q50_prediction'].get('grid_peak')) for r in rows],flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
