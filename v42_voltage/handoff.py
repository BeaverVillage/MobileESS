"""Deterministic individual A1 expansion and exact fixed native M1 inputs."""
from v42_root.common import *
from v42_native.contracts import require
from v42_native.voltage import authority_sha
from .grid import coefficients


def validate_handoff(handoff,anchor):
    require(handoff.get('accepted') is True and handoff.get('known_jobs')==1499 and
            handoff.get('physical_PASS') is True,'A1_HANDOFF_NOT_ACCEPTED')
    require(handoff['anchor_digest']==digest(anchor),'A1_ANCHOR_CHANGED')
    require(anchor['voltage_authority_sha256']==authority_sha(),'A1_ANCHOR_VOLTAGE_DRIFT')
    require(handoff['unknown_individual_jobs_fabricated'] is False,'UNKNOWN_UID_FABRICATION')
    return True


def materialize(m,data,bindings,controls,selected,cert,receipt):
    bundle,jobs,bounds,r,raw,graphs,old,prep=data
    require(receipt['complete'] and cert['PASS'] and set(selected)==set(jobs) and len(jobs)==1499,'A1_HANDOFF_NOT_ACCEPTED')
    rows=[]
    for uid,o in sorted(selected.items()):
        j=jobs[uid];migrated=o['checkpoint']>=0
        rows.append(dict(job_uid=uid,state=j.state,start=o['start'],initial_site=o['initial_site'],
                         completion=o['segments'][-1][2],shift=o['start']-j.reference_start,
                         absolute_shift=abs(o['start']-j.reference_start),prestart_relocation=o['initial_site']!=j.reference_site,
                         migration_selected=migrated,checkpoint=o['checkpoint'],physical_checkpoint_seconds=o['physical_checkpoint_seconds'],
                         source=o['initial_site'],destination=o['destination'],WAN_start=o['transfer_start'],
                         transfer_end=o['transfer_end'],restart=o['restart_end'],full_service_completion=o['segments'][-1][2],
                         GPU=j.gpu,segments=json.dumps(o['segments']),WAN=json.dumps(o['wan']),provisional=True))
    table('A1_PROVISIONAL_CONTROL_TABLE.csv',rows)
    _,coeff=coefficients(bundle);names=list(coeff[0].control_names);cells=[]
    for s in bundle['capacities']:
        i=names.index(f'aidc_load_kw[{s}]')
        for t in range(96):
            actual=t+24;k=value(bindings['known'][s,actual]);u=m.getVarByName(f'anonymous_GPU[{s},{t}]').X
            cells.append(dict(site=s,control_slot=t,issue_origin_slot=actual,known_GPU=k,anonymous_GPU=u,total_GPU=k+u,
                              AIDC_kW=float(controls[t][i]),AIDC_Q_decision=False,
                              Runtime_target=value(bindings['risk'][s,actual]),
                              CC4_reserve_target=m.getVarByName(f'arrival_target_GPU[{s},{t}]').X,
                              CC4_reserve=m.getVarByName(f'CC4_reserve[{s},{actual}]').X,
                              Runtime_reserve=m.getVarByName(f'RT_reserve[{s},{actual}]').X,
                              CC4_shortfall=m.getVarByName(f'CC4_shortfall[{s},{actual}]').X,
                              Runtime_shortfall=m.getVarByName(f'RT_shortfall[{s},{actual}]').X))
    table('A1_AIDC_SITE_TIME_ANCHOR.csv',cells)
    def numeric(obj):
        if isinstance(obj,dict):return {str(k):numeric(v) for k,v in obj.items()}
        if isinstance(obj,(list,tuple)):return [numeric(v) for v in obj]
        try:return value(obj)
        except (TypeError,ValueError):return obj
    unknown=dict(provisional=True,individual_future_jobs=[],fabricated=False,anonymous_site_time=cells,
                 temporal_and_report_state=numeric(bindings['timing']),
                 causal_policy=dict(source='v42_native.actual.unknown_arrival',source_sha256=sha(ROOT/'v42_native/actual.py'),
                                    action_authority='site-only after observation and production Runtime/provider/kernel/capacity gates',
                                    temporal_shift=0,migration_count=0,global_MILP_calls=0,unknown_capabilities_expanded=False,
                                    future_actual_read=False,unpromoted_Runtime_action=None))
    dump('A1_UNKNOWN_POLICY_TABLE.json',unknown)
    anchor=dict(control_names=names,controls=controls,voltage_authority_sha256=authority_sha(),
                fixed_AIDC_control_columns=[i for i,n in enumerate(names) if n.startswith('aidc_load_kw')],
                power_and_PF_source='unchanged frozen native affine C1 and grid coefficient matrices',
                AIDC_Q_decision=False,anonymous_CC4_included=True,provisional=True)
    dump('A1_AIDC_GRID_CONTROL_ANCHOR.json',anchor)
    handoff=dict(accepted=True,physical_PASS=True,known_jobs=len(rows),scientific_classes=len(prep['classes']),
                 individual_expansion=True,unknown_individual_jobs_fabricated=False,unknown_CC4_included=True,
                 anchor_digest=digest(anchor),anchor_file_sha256=sha(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json'),
                 table_sha256=sha(OUT/'A1_PROVISIONAL_CONTROL_TABLE.csv'),unknown_policy_sha256=sha(OUT/'A1_UNKNOWN_POLICY_TABLE.json'),
                 site_time_sha256=sha(OUT/'A1_AIDC_SITE_TIME_ANCHOR.csv'),selected_plan_digest=digest(selected),
                 M1_AIDC_decision_variables=0,final_Actual_table=False)
    validate_handoff(handoff,anchor);dump('A1_TO_M1_HANDOFF.json',handoff)
