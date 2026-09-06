"""Predeclared V40A scientific and saved-data contracts."""
from .invariants import METHOD

ARTIFACT_ROOT='dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt'
DEVELOPMENT_DAY='2025-04-01'
TOLERANCE=1e-6
SEQUENCE=['A0','M1_ROUTE_PQ','A1_FEEDBACK','MF_FIXED_ROUTE_PQ']

CONTRACTS={
 'V40A_METHOD_CONTRACT.json':{'method':METHOD,'paper_name':'Bounded Iterative AIDC–MESS Co-Optimization','sequence':SEQUENCE,
  'feedback_rounds':1,'full_fleet_search_campaign_calls':1,'internal_fleet_search':'INHERITED_FOUR_VEHICLE_ADAPTIVE_BEAM_WITH_K_FALLBACK',
  'global_joint_optimality_claim':False,'convergence_claim':False,'monolithic_claim':False,'tolerance':TOLERANCE,
  'J':'rho_max over all inherited Planning line/phase/time rows','Fresh_inside_loop':False,'Actual_inside_loop':False,
  'development_day':DEVELOPMENT_DAY,'May_result_based_tuning':0,'full_May_launch':False},
 'V40A_CASE_REGISTRY.json':{'B0':'RW reference / MESS OFF','B1':'Current AIDC-only planning authority / MESS OFF',
  'B2':'RW reference / full MESS mobility and P/Q','B3':SEQUENCE,'old_B3_reuse':False,
  'B0_B1_B2_reuse':'DEFERRED_UNTIL_SEPARATE_EXACT_CHANGE_IMPACT_AUDIT'},
 'V40A_AIDC_FEEDBACK_CONTRACT.json':{'primary':'MIN rho_max','secondary':'MIN complete-interval site-time symmetric GPU-slot occupancy deviation',
  'tertiary':'MIN additional RUNNING migrations; identically zero under retained escalation policy','quaternary':'DETERMINISTIC_TIE',
  'RUNNING_mobility_policy':'User confirmed: retain temporal-infeasibility prerequisite; no added migration from feasible A0/M1',
  'RUNNING_A0_decision':'FIXED_IN_A1','PENDING_placement':'existing site GPU and logical Rack compatibility',
  'temporal_eligibility':'D1-visible PENDING standby with SAFE_CAUSAL_RUNTIME_PENDING and RSP_start <= RW_completion - safe_duration',
  'temporal_domain':'RSP_start <= start <= RW_completion - safe_duration, intersect exact A0 post-H profile equality',
  'source_eligibility':'dayahead/tools/run_v39g_day17_shadow.py:eligible_mask','new_SLA_or_deadline':False,
  'MESS_during_A1':'ALL mobility and M1 P/Q FIXED','primary_nondegradation_tolerance':TOLERANCE,
  'solver':{'Threads':4,'Seed':20260905,'MIPGap':0,'MIPGapAbs':0,'FeasibilityTol':1e-8,'IntFeasTol':1e-9,'OptimalityTol':1e-8,'WorkLimit_per_lex_stage':60},
  'WorkLimit_reporting':'incumbent and bound; no global certificate unless solver OPTIMAL'},
 'V40A_FIXED_ROUTE_PQ_RECOURSE_CONTRACT.json':{'mobility_decisions':'FIXED_FROM_M1','route_table_input':False,'route_candidate_enumeration':False,
  'beam_search':False,'K_search':False,'allowed_variables':['P_discharge','P_charge','Q','energy','inherited electrical charge/discharge direction'],
  'physics_source':'dayahead/v33m/mess_mobility_milp.py','grid_source':'dayahead/v34/integrated_mess.py',
  'primary':'MIN rho_max','solver_settings':'inherit _configured_model unchanged','failure':'retain M1 P/Q only when reverified feasible against accepted A1'},
 'V40A_TERMINAL_INVARIANT_CONTRACT.json':{'name':'BASELINE_RELATIVE_PER_JOB_TERMINAL_STATE_PRESERVATION','baseline':'A0 accepted complete job decision',
  'issue_slot_grid_domain':[24,120],'post_H_profile':'UID-wise complete half-open interval, GPU and site equality; no aggregate cancellation',
  'UNASSIGNED':'a frozen state, never permission to invent a future AIDC','new_post_H_occupancy':False,'new_post_H_site':False,'future_day_carry':False},
 'V40A_SAVED_DATA_SCHEMA.json':{'AIDC_required':['job_uid','state_at_issue','qos','requested_GPU','safe_duration_slots','start_slot','end_slot','AIDC_site','Rack_label','migration_selected','migration_destination','terminal_class','post_H_site'],
  'M1_required':['mess_id','slot','mode','origin_service','destination_service','departure_slot','route_link_ids','connection_ready_slot','P_kw','Q_kvar','SoC','battery_energy_kWh','travel_energy_kWh','ETA_Q50','ETA_Q90'],
  'MF_required':['mess_id','slot','P_kw_M1','Q_kvar_M1','P_kw_final','Q_kvar_final','delta_P_kw','delta_Q_kvar','SoC_final'],
  'joint_required':['FINAL_AIDC_DECISION_SHA','FINAL_MESS_ROUTE_SHA','FINAL_MESS_PQ_SHA','FINAL_JOINT_DECISION_SHA']},
 'V40A_RUNTIME_OBSERVABILITY_CONTRACT.json':{'required_stages':['RSP_base_materialization','A0','M1_route_candidate_search','M1_full_MILP','A1','MF','Planning_verification','Fresh','AC_restoration','Total'],
  'required_counters':['AIDC_OPTIMIZATION_PASSES','MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS','FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS','TOTAL_GUROBI_OPTIMIZE_CALLS','TOTAL_ROUTE_CANDIDATES_EVALUATED','TOTAL_RUNTIME_SECONDS'],
  'solver_accounting':'per-process optimize completion events, including beam workers','route_search_count_unit':'ONE_FULL_FLEET_SEARCH_CAMPAIGN; internal vehicle/candidate/MILP calls reported separately'}
}
