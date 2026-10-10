"""Paired development actual-only run after saved SVR4 full96 reproduction.

No optimization, no parameter retuning, no tap/cap setters. Existing replay
source provides isolated Fresh context, full native TIME and immutable inputs.
"""
import argparse,json,sys,time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--source',required=True,type=Path)
p.add_argument('--first4-result',required=True,type=Path)
p.add_argument('--off-result',required=True,type=Path)
p.add_argument('--scenario',required=True,type=Path)
p.add_argument('--output',required=True,type=Path)
a=p.parse_args()
sys.path.insert(0,str(a.source.resolve()))
from v42_pr134_b1.common import read,record,atomic
from v42_b3_joint.contracts import digest
from v42_voltage_control import authority,replay,integration
source=authority.source_files();source_sha=digest(source)
first4=read(a.first4_result)
assert first4['PASS'] is True and first4['status']=='PASS' and first4['configuration']=='SVR4'
assert first4['source_SHA']==source_sha and first4['Native_optimizer_calls']==0
assert first4['metric']['converged_slots']==96
assert not any(first4['metric'][k] for k in ('voltage_violation_cells','line_current_violation_cells','transformer_current_violation_cells','transformer_kva_violation_cells'))
assert first4['metric']['SVR_hardware_PASS_all96'] and first4['metric']['Original7_AUTO_all96'] and first4['metric']['Fixed_ON_original_caps_all96']
for key in ('raw_AC','physical_audit'): authority.checked(first4[key])
off=read(a.off_result)
assert off['OFF_original_AC_bit_exact'] is True and off['source_SHA']==source_sha
scenario=read(a.scenario);integration.validate_scenario(scenario)
assert scenario['svr']['status']=='DEVELOPMENT_NOT_FROZEN_NOT_CANARY'
assert [u['id'] for u in scenario['svr']['units']][:6]==['STA01','STA06','STA08','BUS83','BUS79','BUS108']
assert [u['id'] for u in scenario['svr']['units']][6:] in (['BUS48'],['BUS50'])
first4path=authority.checked(first4['infrastructure'])
four=read(authority.checked(read(first4path)['scenario']))
assert scenario['svr']['units'][:4]==four['svr']['units']
assert scenario['connection_manifest']==four['connection_manifest']
request=Path(off['original_bindings'][0]['path'])
operations=Path(off['original_bindings'][1]['path']).parent.parent
before=[record(a.first4_result),record(a.off_result),record(a.scenario)]
t0=time.perf_counter()
r=replay.run_frozen(request,operations,a.output,scenario_path=a.scenario,off_result_path=a.off_result,development=True)
gate=dict(source_SHA=r['source_SHA'],scenario_SHA=r['scenario_SHA'],arm=r['arm'],day=r['day'],raw_AC_receipt=r['raw_AC_receipt'],physical_audit=r['physical_audit'])
strict_gate_pass=None;strict_gate_error=None
try:
    authority.verify_physical_gate(gate)
    strict_gate_pass=True
except PermissionError as error:
    strict_gate_pass=False;strict_gate_error=str(error)
assert authority.source_files()==source
assert [record(a.first4_result),record(a.off_result),record(a.scenario)]==before
summary=dict(schema='V42_SVR7_PAIRED_KNOWN_DATE_DEVELOPMENT_RESULT_V1',source_SHA=source_sha,scenario_SHA=r['scenario_SHA'],alternative=scenario['svr']['units'][-1]['id'],arm=r['arm'],day=r['day'],case='B',time_mode='TIME',status=('PASS' if r['Full_AC_Physical_PASS'] and strict_gate_pass else 'PHYSICAL_FAIL'),PASS=r['Full_AC_Physical_PASS'] and strict_gate_pass,strict_saved_physical_gate_PASS=strict_gate_pass,strict_saved_physical_gate_error=strict_gate_error,metrics={k:v for k,v in r['metrics'].items() if k!='violations'},physical_audit=r['physical_audit'],raw_AC_receipt=r['raw_AC_receipt'],replay_result=record(a.output/'REPLAY_RESULT.json'),first_SVR4_reproduction=before[0],OFF_static_bitexact_proof=before[1],candidate_scenario=before[2],source_and_inputs_before_after_exact=True,all_original_inputs_unchanged=r['original_inputs_unchanged'],Native_optimizer_calls=0,Actual_reoptimization=0,MESS_PQ_repair=0,Planning_reoptimized=False,new_model_E2E_qualified=False,holdout_claim=False,measurement_scope='96 chronological slot-end all original+added node/current/TX readback; not continuous transient certification',wall_seconds=time.perf_counter()-t0)
atomic(a.output/'CANDIDATE_DEVELOPMENT_RESULT.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
