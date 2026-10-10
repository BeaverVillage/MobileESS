"""Read-only verification of the user's 31 B0 + 6 B2 handoff condition."""
from pathlib import Path
import sys,math,json
import numpy as np
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic,read,record,now,sha
from v42_svr11.authority import verify

TARGETS=[('B0',f'2025-05-{d:02d}') for d in range(1,32)]+[('B2',f'2025-05-{d:02d}') for d in range(1,7)]

def require(value,reason):
    if not value:raise ValueError(reason)

def checked(r,owned):
    p=Path(r['path']).resolve()
    require(p.is_relative_to(owned),'HANDOFF_EVIDENCE_OWNERSHIP')
    require(record(p)==r,'HANDOFF_EVIDENCE_SHA_DRIFT:'+str(p))
    return p

def audit_date(root,m,row):
    arm,day=row['arm'],row['day'];result_path=Path(row['result']);attempt=result_path.parent
    require(attempt.is_relative_to(root/'dates'/arm/day/'attempts'),'HANDOFF_ATTEMPT_OWNERSHIP')
    require(sha(result_path)==row['result_SHA'],'HANDOFF_RESULT_SHA_DRIFT')
    r=read(result_path);require(r['PASS'] is True and r['status']=='PASS','HANDOFF_ACTUAL_DATE_PASS_REQUIRED')
    require(r['source_SHA']==m['execution_SHA'] and r['identity']['arm']==arm and r['identity']['day']==day
        and r['identity']['run_id']==m['run_id'],'HANDOFF_DATE_SOURCE_IDENTITY')
    require(r.get('Actual_PQ_repair')==r.get('Actual_reoptimization')==0,'HANDOFF_ACTUAL_REPAIR_FORBIDDEN')
    receipts=[record(result_path)];namespaces={};output=attempt/'output'
    for ar in r['metrics']['evidence']:
        ap=checked(ar,output);a=read(ap)
        require(a['source_SHA']==m['execution_SHA'] and a['scenario_SHA']==read(m['scenario']['path'])['scenario_SHA']
            and a['day']==day and a['arm']==arm,'HANDOFF_PHYSICAL_SOURCE_IDENTITY')
        require(a['status']=='COMPLETE' and a['logical_Fresh_slots']==96 and a['Full_AC_Physical_PASS'] is True
            and a['hardware_and_controller_PASS'] is True,'HANDOFF_COMPLETE_96_PHYSICAL_REQUIRED')
        require(a['Actual_optimizer_calls']==a['Actual_plan_repair_calls']==0 and a['DSTATCOM_object_count']==0
            and a['Planning_Tap_or_Cap_state_transfer_to_Actual'] is False,'HANDOFF_INDEPENDENT_AUTO_CONTROL_REQUIRED')
        sp=checked(a['slots_receipt'],output);slots=read(sp)
        require([s['slot'] for s in slots]==list(range(96)),'HANDOFF_SLOT_AXIS')
        node_axis=None;vmin=math.inf;vmax=-math.inf;peak_line=0.
        for s in slots:
            p=s['physical'];controls=s['settled_original_controls']
            require(s['PASS'] is True and p['all_original_and_added_axes_checked'] is True
                and controls['solution_converged'] is True and s['control_actions_done_as_of_current_time'] is True,
                'HANDOFF_AC_OR_CONTROL_FAILURE')
            axis=[n['node_phase'] for n in p['nodes']]
            if node_axis is None:node_axis=axis
            require(axis==node_axis,'HANDOFF_ALL_NODE_PHASE_AXIS_DRIFT')
            vs=[n['voltage_pu'] for n in p['nodes']]
            require(all(math.isfinite(v) and .95<=v<=1.05 for v in vs),'HANDOFF_LITERAL_FULL_NODE_PHASE_VOLTAGE_FAIL')
            vmin=min(vmin,min(vs));vmax=max(vmax,max(vs))
            for c in p['currents']:
                require(c['terminal'] in (1,2) and math.isfinite(c['current_A']) and c['current_A']>=0
                    and c['NormalAmps']>0 and c['current_A']<=c['NormalAmps'],'HANDOFF_LITERAL_BOTH_TERMINAL_CURRENT_FAIL')
                if c['nameplate_current_A'] is not None:
                    require(c['current_A']<=c['nameplate_current_A'],'HANDOFF_NAMEPLATE_PHASE_CURRENT_FAIL')
                if c['element'].startswith('line.'):peak_line=max(peak_line,c['loading_pu'])
            require(all(t['rating_kVA']>0 and math.isfinite(t['kVA']) and t['kVA']<=t['rating_kVA'] for t in p['transformers']),
                'HANDOFF_BOTH_TERMINAL_TRANSFORMER_KVA_FAIL')
            devices=s['svr']['devices']
            require(len(devices)==11 and len(controls['original_regulators'])==7 and len(controls['capacitors'])==4
                and len(controls['capcontrols'])==0,'HANDOFF_FROZEN_DEVICE_COUNTS')
            require(all(d['hardware_PASS'] is True and len(d['phases'])==3
                and all(x['autonomous_control_enabled'] is True and x['tap_range_PASS'] is True and .9<=x['tap']<=1.1
                    for x in d['phases']) for d in devices),'HANDOFF_SVR11_FINITE_AUTO_TAP_FAIL')
        namespaces[a['namespace']]=dict(slots=96,all_node_phase_count=len(node_axis),Vmin=vmin,Vmax=vmax,
            maximum_line_loading=peak_line,Full_AC_Physical_PASS=True)
        receipts.extend([ar,a['slots_receipt']])
    require(set(namespaces)=={'DAYAHEAD','ACTUAL'},'HANDOFF_BOTH_PLANNING_AND_ACTUAL_REQUIRED')
    raw=list(output.rglob('OPENDSS_PHASE_ARRAYS.npz'))
    require(len(raw)>=2,'HANDOFF_BOTH_FRESH_ARRAYS_REQUIRED')
    for p in raw:
        with np.load(p,allow_pickle=False) as z:
            require(z['convergence'].shape==(96,) and bool(z['convergence'].all()),'HANDOFF_FRESH_96_CONVERGENCE')
            for name in ('voltage_pu','phase_current_a','phase_current_loading_pu','transformer_total_kva_loading_pu'):
                values=z[name]
                if name=='transformer_total_kva_loading_pu':
                    # Original arrays intentionally use NaN on LINE columns.
                    values=values[:,np.asarray(z['branch_kinds'])=='transformer']
                require(values.shape[0]==96 and np.isfinite(values).all(),'HANDOFF_FRESH_FULL_AXIS:'+name)
        receipts.append(record(p))
    isolations=list(output.rglob('PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json'))
    require(len(isolations)==1,'HANDOFF_CONTROL_ISOLATION_REQUIRED');isolation=read(isolations[0])
    require(isolation['PASS'] is True and isolation['source_SHA']==m['execution_SHA']
        and isolation['Planning_and_Actual_engine_objects_distinct'] is True
        and isolation['Planning_Tap_Cap_queue_or_controller_state_transferred'] is False,'HANDOFF_CONTROL_STATE_TRANSFER')
    receipts.append(record(isolations[0]))
    if arm=='B2':
        science=r['scientific'];require(science['feasible_accepted'] is True and science['accepted'] is True
            and science['source_SHA']==m['execution_SHA'],'HANDOFF_CURRENT_FULL_M_FEASIBLE_REQUIRED')
        ub=read(checked(science['certificate']['strict_UB'],output))
        require(ub['PASS'] is True and ub['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact'] is True
            and ub['original_matrix_and_96_slot_physical_replay']['PASS'] is True
            and ub['case_sha']==science['case_sha'],'HANDOFF_INDEPENDENT_FULL_M_CERTIFICATE')
        receipts.append(science['certificate']['strict_UB'])
    return dict(PASS=True,arm=arm,day=day,source_SHA=m['execution_SHA'],result_SHA=row['result_SHA'],
        namespaces=namespaces,Fresh_original_arrays_count=len(raw),evidence=receipts,
        optimization_status=r.get('optimization_status'),global_gap_certified=r.get('global_gap_certified'),
        Native_Runtime=r.get('Native_Runtime'),wall_seconds=r.get('wall_seconds'),UTC=now())

def run(root):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
    final_check=all(ledger['dates'][a+'/'+d]['status']=='PASS' for a,d in TARGETS)
    folder=root/'handoff37';folder.mkdir(exist_ok=True);dates=[]
    for arm,day in TARGETS:
        row=ledger['dates'][arm+'/'+day];cache=folder/(arm+'_'+day+'.json')
        if row['status']!='PASS':
            dates.append(dict(arm=arm,day=day,PASS=False,status=row['status'],reason=row.get('reason')));continue
        try:
            previous=read(cache) if cache.exists() else None
            if previous and previous['source_SHA']==m['execution_SHA'] and previous['result_SHA']==row['result_SHA']:
                # Complete immutable attempts are verified once while waiting;
                # all protected bytes are rehashed before the final handoff.
                if final_check:require(all(record(r['path'])==r for r in previous['evidence']),'HANDOFF_CACHED_RECEIPT_DRIFT')
                v=previous
            else:v=audit_date(root,m,row);atomic(cache,v)
            dates.append(v)
        except Exception as error:dates.append(dict(arm=arm,day=day,PASS=False,status='VERIFICATION_FAILED',error=repr(error)))
    passed=sum(d['PASS'] is True for d in dates)
    result=dict(schema='SVR11_USER_HANDOFF_37_V1',PASS=passed==37,verified_PASS=passed,total=37,
        final_all_receipt_bytes_reverified=bool(final_check and passed==37),
        source_SHA=m['execution_SHA'],campaign_root=str(root),verifier=record(Path(__file__)),dates=dates,
        campaign_processes_terminated=0,Native_optimizer_calls=0,UTC=now())
    atomic(root/'HANDOFF_37_VALIDATION.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='dates'},ensure_ascii=False))
    print(json.dumps([d for d in dates if d.get('status') in ('FAIL','VERIFICATION_FAILED')],ensure_ascii=False))
    return result

if __name__=='__main__':run(sys.argv[1])
