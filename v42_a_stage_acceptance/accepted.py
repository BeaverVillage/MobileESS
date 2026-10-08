"""Freeze only after complete original physical replay and all four gates."""
from fractions import Fraction
from pathlib import Path
import numpy as np
from v42_pr134_b1.common import read,atomic,record,digest
from v42_a_stage_lexfull.runner import objective_value
from v42_a_stage_domain_v2.lexstage import rebuild_locked_snapshot
from v42_a_stage_phase1.core import primal_replay
from .policy import OUT,STATIC
from .execution import active_freeze

def freeze(day,state,original,point,physical,locks,certificates):
    f=OUT/day
    if len(certificates)!=4:raise ValueError('FOUR_OBJECTIVE_CERTIFICATES_REQUIRED')
    for c in certificates:
        if record(c['path'])!=c or not read(c['path']).get('PASS'):raise ValueError('CURRENT_A1_OBJECTIVE_CERTIFICATE_DRIFT')
    replay=physical.verify(point);locked,lockproof=rebuild_locked_snapshot(original,locks)
    rows=primal_replay(locked,point)
    if not replay['PASS'] or not rows['PASS']:raise ValueError('FINAL_COMPLETE_ORIGINAL_A1_REPLAY_FAILED')
    values={name:objective_value(original,point,name) for name in ('rho','migration_count','shift_magnitude','prestart_relocation')}
    if set(replay['selected_jobs'])!=set(state['data'][1]):raise ValueError('ORIGINAL_JOB_POPULATION_RECONSTRUCTION_REQUIRED')
    from .schedule_audit import original_schedule_metrics
    original_schedule_metrics(state['data'][1],replay['selected_jobs'],values)
    atomic(f/'FINAL_PHYSICAL_REPLAY.json',replay);atomic(f/'FINAL_SEQUENTIAL_LOCKS.json',dict(PASS=True,proof=lockproof,replay=rows))
    sites=sorted(state['data'][3].capacities);controls=np.asarray(replay['controls']);coeff=physical.coeff
    power=np.asarray([[controls[t,coeff[t].control_names.index('aidc_load_kw['+site+']')] for site in sites] for t in range(len(controls))])
    q=STATIC/day/'FROZEN_A1_ARRAYS.npz';q.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(q,X=point,controls=controls,site_time_power_kw=power,sites=np.asarray(sites))
    frozen=dict(PASS=True,A1_ACCEPTED=True,scientific_status='SCIENTIFIC_ACCEPTED',day=day,
        selected_jobs=replay['selected_jobs'],original_job_population=sorted(state['data'][1]),
        original_jobs_count=len(state['data'][1]),site_time_power_arrays=record(q),
        control_names=list(coeff[0].control_names),objective_values={k:float(v) for k,v in values.items()},
        exact_objective_values={k:str(v) for k,v in values.items()},certificates=certificates,
        physical=record(f/'FINAL_PHYSICAL_REPLAY.json'),sequential_locks=record(f/'FINAL_SEQUENTIAL_LOCKS.json'),
        source=record(active_freeze()),original_model_sha256=original.fingerprint(),
        scientific_bundle_sha256=digest(state['data'][0]),original_job_ids_sha256=digest(sorted(state['data'][1])),
        original_input=record(Path('C:/v42_pr134_sc_execution_20261007/inputs')/day/'NATIVE_INPUT.json'),
        PR134_freeze_reused=False,physical_rules_changed=False)
    atomic(f/'FROZEN_A1.json',frozen)
    result=dict(A1_accepted=True,classification='SCIENTIFIC_ACCEPTED',day=day,
        objective_values=frozen['objective_values'],certificates=certificates,frozen_A1=record(f/'FROZEN_A1.json'))
    atomic(f/'A1_RESULT.json',result);print('A1_FROZEN_ACCEPTED',day,result['frozen_A1']['sha256'],flush=True)
    return result
