from .common import *
from datetime import datetime

def main():
    assert git('rev-parse','HEAD')==START
    assert git('rev-parse','HEAD^')=='3a6ab4fa369a9f8e16203af62b1b00bf56666716'
    assert git('branch','--show-current')=='codex/v40r3-causal-gpuwork-arrival-ml'
    prior=Path('C:/codex_mobileess_workspace/MobileESS_v40r_causal_dayahead_workload/dayahead/artifacts/v40r_causal_dayahead_workload')
    refs=json.loads((prior/'V40R_V40P_FREEZE_VERIFICATION.json').read_text(encoding='utf-8'))
    checks=[]
    for group in ['reference_checks','model_checks']:
        for row in refs.get(group,[]):
            path=row['path'].replace('\\','/'); value=hashlib.sha256(blob(path)).hexdigest()
            expected=row.get('SHA256',row.get('expected_SHA256'))
            assert value==expected
            checks.append({'path':path,'SHA256':value,'match':True,'group':group,'read':'byte hashing, no scientific payload decoding'})
    dump('V40R3_V40P_REFERENCE_FREEZE.json',{'classification':'V40P_FORECAST_CAUSALITY_FAIL','start':START,'all_match':True,
      'reference_count':sum(c['group']=='reference_checks' for c in checks),'model_count':sum(c['group']=='model_checks' for c in checks),'checks':checks})
    worktrees={}
    for entry in git('worktree','list','--porcelain').split('\n\n'):
        lines=entry.splitlines()
        if not lines:continue
        path=lines[0].removeprefix('worktree ')
        if any(key in path.lower() for key in ['v40p_','v40r_','v40r2_','v40s_','v40s2_']):
            if Path(path).exists():
                worktrees[path]={'HEAD':git('rev-parse','HEAD',cwd=path),'status':git('status','--porcelain',cwd=path),
                    'access':'HEAD/status metadata only; V40R/R2 explicitly allowlisted references remain read-only'}
    dump('V40R3_START_STATE.json',{'time_UTC':datetime.now(timezone.utc).isoformat(),'start':START,'research_reference':'3a6ab4fa369a9f8e16203af62b1b00bf56666716',
      'branch':git('branch','--show-current'),'worktree':ROOT,'initial_clean_verified':True,'protected_worktree_start':worktrees,
      'V40R2_status':'SUPERSEDED_BY_V40R3; user-interrupted experiment preserved as-is; no fitting, resumption, code reuse, merging, deletion or further writes',
      'May_inherited_context':'V40P broad source incident remains disclosed; this is not a clean-room task',
      'protected':['V40I/J/K/L/M/N/P/Q/R/R2/S/S2','K0','T7','optimizer','electrical','production q','B0-B3','Full May']})
    paths=['pfr/contracts/SLOW_FAST_CONTROLLER_CONTRACT.json','pfr/contracts/AI_TRAINING_MODEL.json',
      'pfr/contracts/HIERARCHICAL_MOVE_BLOCKED_MIXED_INTEGER_MPC_V1.json','r26/config/r26_contract.json','r26/config/event_config.example.json',
      'pfr/slow_fast.py','dayahead/aidc_service_contract.py','dayahead/v36/contracts.py','dayahead/v37/aidc_materializer.py']
    evidence=[]
    for path in paths:
        b=blob(path); lines=b.decode('utf-8').splitlines()
        needles=['replanning_interval_minutes','grid_minutes','remaining_work_gpu_hours','executed =','remaining[job_id]',
          'work_unit','initial_work_formula','five_minute_progress_formula','cadence_seconds','max_refresh_steps','AEST =','def issue_time','timedelta(hours=6)',
          'backlog.append','cumulative_processed > cumulative_arrival']
        evidence.append({'path':path,'SHA256':hashlib.sha256(b).hexdigest(),
          'excerpts':[{'line':i+1,'text':line} for i,line in enumerate(lines) if any(n in line for n in needles)]})
    slow=json.loads(blob(paths[0])); hierarchy=json.loads(blob(paths[2])); assert slow['replanning_interval_minutes']==hierarchy['slow_master']['grid_minutes']==30
    dump('V40R3_DOWNSTREAM_WORKLOAD_CONTRACT_AUDIT.json',{'status':'RECOVERED_WITH_INTERFACE_LIMITS','before_target_resolution':True,
      'slow_scheduling_grid_minutes':30,'event_observation_interval_minutes':5,'maximum_refresh_minutes':30,
      'fast_service_step_minutes':5,'DayAhead_existing_planner_grid_minutes':15,
      'R26_multires_route_grid':'5 minutes for first hour, 15 thereafter; route stages are distinct from the 30-minute workload slow-master contract',
      'work_units':'Original PFR normalized GPU-hour accounting; V40R3 unnormalized observed authorized GPUh proxy, not hardware-independent work',
      'initial_work':'required_gpu_count * baseline_runtime_hours','service_progress':'remaining_next=max(0,remaining - gpu_count*compute_rate_fraction*5/60)',
      'aggregate_conservation':'B[k+1]=B[k]+Delta_W[k]-S[k], S cannot exceed arrived available work',
      'legacy_DayAhead_adapter':'96x15-min H100-node-hour increments, backlog conservation; conversion is NOT reused for R3 GPU counts',
      'cumulative_vs_incremental':'Legacy K5B2 independently predicted cumulative horizons. Downstream service accounting subtracts work increments; cumulative availability derives by summation.',
      'R3_target_intervals':48,'R3_interval_minutes':30,'integration_authorized':False,
      'forecast_origin':'D-1 18:00 fixed AEST = D-1 08:00 UTC','operating_day':'D 00:00..D+1 00:00 fixed AEST; [start,end)',
      'evidence':evidence,'authority_read_scope':'Allowlisted code/config; some January development runtime commentary was exposed in the hierarchical contract; no May scientific outcomes read'})
    print('Exact lineage, frozen references, protected metadata and 30-minute GPUh slow-layer contract recorded.')

if __name__=='__main__':main()
