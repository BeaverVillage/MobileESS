"""New immutable raw-input epoch; no historical decisions/models are admitted."""
from pathlib import Path
import copy,shutil,subprocess
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import ROOT,source_files,VERSION
SCHEMA='V42_COMMON_U4_QUALIFICATION_V1'
from . import DAYS,ORDER

ORIGIN=Path(r'D:\v42_may_restart_20261010_02\B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json')
RAW=('PLANNING_INPUT_BUNDLE.json','ACTUAL_INPUT_BUNDLE.json','POWER_AUTHORITY.json','SOURCE_PROVENANCE.json','C1_PLANNING_COEFFICIENTS.csv','ROUTE_TABLE.json.gz','TRAFFIC_FORECAST.npz','DERIVED_AEMO_ACTUAL.parquet','DERIVED_NOAA_ACTUAL.parquet')

def raw(root):
    root=Path(root).resolve();m=read(ORIGIN);origins={};receipts={}
    for day in DAYS:
        source=Path(m['input_folders'][day]);dest=root/'raw'/day;dest.mkdir(parents=True,exist_ok=True)
        copied=[]
        for name in RAW:
            if (source/name).is_file():
                if not (dest/name).exists():shutil.copyfile(source/name,dest/name)
                if record(source/name)['sha256']!=record(dest/name)['sha256']:raise PermissionError('SVR11_RAW_COPY_DRIFT')
                copied.append(record(dest/name))
        # B0/B2 native skeleton contains only descriptors and immutable authorities.
        shutil.copyfile(source/'NATIVE_INPUT.json',dest/'NATIVE_INPUT_TEMPLATE_B2.json')
        final=read(m['inherited_B1_results']['B1/'+day]['path'])
        freeze=next(r for r in final['files'] if Path(r['path']).name=='A_NATIVE_SOURCE_FREEZE.json')
        b1=Path(freeze['path']).parent;frozen=read(freeze['path']);inputs=Path(frozen['inputs']['NATIVE_INPUT.json']['path']).parent
        for name in ('NATIVE_INPUT.json','WINDOWS.json'):
            shutil.copyfile(inputs/name,dest/(name.replace('.json','_TEMPLATE_B1.json') if name=='NATIVE_INPUT.json' else name))
        ops=read(inputs/'OPERATIONS.json')
        atomic(dest/'OPERATIONS_TEMPLATE_B1.json',ops)
        atomic(dest/'OPERATIONS_TEMPLATE_B2.json',dict(current_day_folder=str(dest),forecast_inputs=read(dest/'PLANNING_INPUT_BUNDLE.json')['forecast_inputs']))
        origins[day]=dict(domain_source=str(b1),historical_B1_result=m['inherited_B1_results']['B1/'+day],
            permitted_reuse='Immutable job domain roster and raw descriptors only; no historical point, bound, control, AC, or electrical model reuse',
            raw_original=[record(source/n) for n in RAW if (source/n).is_file()])
        receipts[day]=[record(p) for p in sorted(dest.iterdir()) if p.is_file()]
    atomic(root/'RAW_INPUT_ORIGINS.json',origins)
    atomic(root/'RAW_INPUT_RECEIPTS.json',receipts)

def release(root):
    root=Path(root).resolve();manifest=root/'CAMPAIGN_MANIFEST.json'
    if manifest.exists():raise PermissionError('SVR11_SOURCE_EPOCH_RELEASE_NEVER_OVERWRITTEN')
    source=source_files();hpath=root/'hardware/HARDWARE.json';h=read(hpath)
    # Retain the initial implementation smoke receipt, bind those exact physical
    # readbacks to the final executable release without repeating AC experiments.
    atomic(root/'hardware/PROVISIONAL_IMPLEMENTATION_FREEZE.json',h)
    h.update(source_SHA=digest(source),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_release_UTC=now(),provisional_receipt=record(root/'hardware/PROVISIONAL_IMPLEMENTATION_FREEZE.json'))
    atomic(hpath,h)
    atomic(root/'B3_SOURCE_SEAL.json',dict(schema='B3_AUTONOMOUS_SOURCE_SEAL_V1',root=str(ROOT),source_sha=digest(source),files=source))
    m=dict(schema=SCHEMA,svr11_campaign=True,authorization='V42_FINAL_USER_20261011',run_id='SVR11_FINAL_MAY_'+root.name,root=str(root),code_root=str(ROOT),
        execution_sources=source,execution_SHA=digest(source),source_commit=h['source_commit'],algorithm_version=VERSION,
        native_M_limit_seconds=1800,native_A_limit_seconds=5400,A_gap=.005,A_anytime_FULL_feasible=True,A_gap_certificate_required=False,normal_TIMEOUT_restart=False,retry_new_attempt_starts_zero=True,retry_max_attempts=3,retry_authority="USER_EXPLICIT_RESTART_FROM_ZERO_20261011",M_acceptance='FULL_FEASIBLE_UB',M_gap_certificate_required=False,
        Threads=1,P2_calls=0,policy_order=list(ORDER),worker_counts=dict(B0=1,B2=3,B1=1,B3=1),FAIL_CONTINUE=True,
        hardware=record(hpath),scenario=record(root/'hardware/SCENARIO.json'),thermal=record(root/'hardware/THERMAL.json'),
        input_receipts=read(root/'RAW_INPUT_RECEIPTS.json'),origins=read(root/'RAW_INPUT_ORIGINS.json'),
        implementation=dict(version='B2_BUILD_SOURCE_AUTHORITY_V13_20261009',sources=source),builder_original_sources=source,
        Actual_reoptimization=0,Actual_PQ_repair=0,Planning_taps_copied_to_Actual=False,monthly_precanary=False,
        retrospective_design=True,independent_holdout_claim=False,predecessor_commit='a26133a8983b625c7ba589c67a40c6576e796247',predecessor_PR=206,UTC=now())
    atomic(manifest,m)
    from .authority import verify
    verify(manifest)
    return m

if __name__=='__main__':
    import sys
    (raw if sys.argv[1]=='raw' else release)(sys.argv[2])
