#!/usr/bin/env python3
from pathlib import Path
import ast,hashlib,json,subprocess,sys,re
R=Path(__file__).resolve().parent;C=json.loads((R/"BUILD7B_CONTRACT.json").read_text())
def s(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
 return h.hexdigest()
c={"ar2_sha":s(R/"embedded/BUILD7AR2_PASS.tar.gz")==C["parents"]["BUILD7AR2"],
   "b6_sha":s(R/"embedded/BUILD6R3R5_PASS.tar.gz")==C["parents"]["BUILD6R3R5"],
   "sa_sha":s(R/"embedded/SOURCEAUTH_FIX1R1_PASS.tar.gz")==C["parents"]["SOURCEAUTH_FIX1R1"]}
for n in ["main.py","EXACT_GRID_RUNNER_24SERVICE.py","ensure_failure.py","write_checksums.py","r25d_radial_projection.py","r25d_radial_projection_proof_test.py","r25e_node_arc_exact.py","r25e_node_arc_exact_proof_test.py","r25h_b1_certificate_policy_proof_test.py","r25i_b2_numerical_rescaling_proof_test.py","r25j_b3_miqcp_kernel_screen_proof_test.py","r25k_b4_root_branch_strengthening_proof_test.py","r25m_b6_exact_path_decomposition.py","r25m_b6_exact_path_decomposition_proof_test.py","r25m_b6r1_objval_lifecycle_proof_test.py","r25m_b6r2_batch_pricing_numerical_guard_proof_test.py","r25m_b6c4_strong_branching_proof_test.py","r25n_b6c5r4_numerical_conditioning_polish_proof_test.py","r25n_b6c5r4_gurobi_polish_smoke.py","r25o_b6c5r4r1_gurobi_unit_equivalence_smoke.py","r25p_stage1_unlimited_completion_proof_test.py","r25p_unlimited_gurobi_policy_smoke.py","r25q_numerical_envelope_resume_proof_test.py","r25r_retained_optimal_dual_resume_proof_test.py"]:
 ast.parse((R/n).read_text());c["syntax_"+n]=True
x=(R/"main.py").read_text()
for t in ["profile_safe_horizon_steps","global_departure_prefix_reserve_kWh","pareto_moves","support_debt_terminal",
          "workload_debt_terminal","safe_netP_bus_kW","safe_Q_bus_kvar","ratio2_ref","lineS_",
          "mess_location_service_id","exact_profile_cert","Fresh_Exact_OpenDSS_24service_firststep_pass",
          "single_issue_full_54step_joint_master_executed","full_54step_joint_master_executed",
          "future_actual_used_for_optimizer","K9H7_RESULT_V1_DATA"]:
 c["guard_"+t[:45]]=t in x
g=(R/"EXACT_GRID_RUNNER_24SERVICE.py").read_text()
c["grid_service_api"]="mess_location_service_id" in g and "MESS_DIS_{sid}" in g and "MESS_CHG_{sid}" in g
cp=subprocess.run([sys.executable,str(R/"main.py"),"--self-test"],capture_output=True,text=True,check=True)
c["semantic_selftest"]=json.loads(cp.stdout)["PASS"]

# BUILD7BR1 exact failure regression and mv-key arity guard.
fail_arc=R/"embedded/BUILD7B_FAILURE_ARITY_AUTHORITY.tar.gz"
c["build7b_failure_sha"]=s(fail_arc)=="ac391f1037bc656fa1e7154c13185d5ca933f1b8d87b394fe5ecc6a4877adcd8"
import tarfile,tempfile,shutil
td=tempfile.mkdtemp(prefix="b7br1_rel_")
try:
 with tarfile.open(fail_arc,"r:gz") as tf:
  try: tf.extractall(td,filter="data")
  except TypeError: tf.extractall(td)
 fs=list(Path(td).rglob("_FAILURE.json"))
 c["failure_json_unique"]=len(fs)==1
 if fs:
  f=json.loads(fs[0].read_text())
  c["failure_semantics"]="too many values to unpack (expected 2)" in f.get("error","") and "line 335" in f.get("traceback","")
finally:
 shutil.rmtree(td,ignore_errors=True)
main_text=(R/"main.py").read_text()
c["old_bad_depflag_removed"]="depflag=gp.quicksum(mv[(mid,h,slot)] for (hh,slot) in mv if hh==h)" not in main_text
c["new_3tuple_depflag_present"]="depflag=gp.quicksum(v for (m0,hh,slot),v in mv.items() if m0==mid and hh==h)" in main_text
# All direct iterations over mv keys/items in build_full must use the 3-field key.
tree=ast.parse(main_text)
bf=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="build_full")
bad_mv_target=[]
for n in ast.walk(bf):
 if isinstance(n,(ast.comprehension,ast.For)):
  it=n.iter
  is_mv=False
  if isinstance(it,ast.Name) and it.id=="mv": is_mv=True
  if isinstance(it,ast.Call) and isinstance(it.func,ast.Attribute) and isinstance(it.func.value,ast.Name) and it.func.value.id=="mv" and it.func.attr=="items": is_mv=True
  if is_mv:
   target=n.target
   # mv direct keys are 3-tuples; mv.items targets are (3-tuple, value).
   if isinstance(it,ast.Name):
    ok=isinstance(target,ast.Tuple) and len(target.elts)==3
   else:
    ok=(isinstance(target,ast.Tuple) and len(target.elts)==2 and
        isinstance(target.elts[0],ast.Tuple) and len(target.elts[0].elts)==3)
   if not ok: bad_mv_target.append(ast.dump(target,include_attributes=False))
c["mv_key_arity_static_audit"]=not bad_mv_target


logp=R/"embedded/BUILD7BR1_ABRUPT_STOP_LOG_AUTHORITY.txt"
c["br1_abrupt_log_sha"]=s(logp)==C["parent_BUILD7BR1_abrupt_log_sha256"]
lt=logp.read_text(errors="ignore")
c["br1_abrupt_signature"]=("Presolved model has 1705 quadratic constraint(s)" in lt and
 "Variable types: 16873 continuous, 113854 integer (113833 binary)" in lt and
 "Traceback" not in lt and "ONLY_HANDOFF_FILE" not in lt)
mt=(R/"main.py").read_text()
for token in ["m.Params.MIQCPMethod=_miqcp_method","PreSparsify=2","NodefileStart=0.5","SoftMemLimit=soft_mem_gb",
              "BUILD7BR2_PREOPT_MODEL_AUDIT.json","_LIVE_HEARTBEAT.json",
              "FP[(h,n)]==ownP[n]","FQ[(h,n)]==ownQ[n]","dU[(h,n)]==dU[(h,p)]",
              "svcS_{h}_{sid}","reachable_by_mid","m.dispose()","GRB.MEM_LIMIT"]:
 c["br2_guard_"+token[:40]]=token in mt
c["dense_recursive_grid_removed"]="absP=dict(ownP);absQ=dict(ownQ)" not in mt


fa=R/"embedded/BUILD7BR2_KEYERROR_AUTHORITY.tar.gz";fl=R/"embedded/BUILD7BR2_KEYERROR_LOG_AUTHORITY.txt"
c["br2_failure_sha"]=s(fa)==C["parent_BUILD7BR2_failure_archive_sha256"];c["br2_log_sha"]=s(fl)==C["parent_BUILD7BR2_failure_log_sha256"]
lt=fl.read_text(errors="ignore");c["br2_keyerror_semantics"]=("KeyError(('MESS01', 0, 70))" in lt and "mv[(mid,h,slot)]" in lt)
mt=(R/"main.py").read_text();c["reachable_mv_depart_present"]='depart=gp.quicksum(float(moves[(h,slot)]["energy_kWh"])*v for (m0,hh,slot),v in mv.items() if m0==mid and hh==h)' in mt;c["old_unpruned_depart_removed"]='depart=gp.quicksum(float(mm["energy_kWh"])*mv[(mid,h,slot)]' not in mt;c["mv_domain_audit_present"]="BUILD7BR3_MV_DOMAIN_AUDIT.json" in mt
tr=ast.parse(mt);bf=next(n for n in tr.body if isinstance(n,ast.FunctionDef) and n.name=="build_full")
# BR7 removed repeated O(|mv|) construction scans by building mv_by_mid_h. Later direct
# mv[...] lookups in warm-start/extraction are intentional O(1) dictionary access and must
# not make the release self-test fail.
c["no_quadratic_mv_construction_scan"]='for (m0,hh,slot),v in mv.items() if m0==mid and hh==h' not in mt
c["indexed_mv_lookup_active"]='mv_by_mid_h=defaultdict(list)' in mt
# R24 exact-rebase static guards.
c["r24_exact_rebase_flag"]='MOBILEESS_R24_PERMANENT_EXACT_REBASE' in mt
c["r24_stay_projection"]='vtype=GRB.CONTINUOUS,name="stay"' in mt
c["r24_debt_suffix_cuts"]='r24_debt_suffix_' in mt
c["r24_soc_prefix_cuts"]='r24_soc_prefix_' in mt
c["r24_onepass_b5"]='extract_b5_rolling_once' in mt
c["r24_no_sos_added"]='addSOS' not in mt
# R25D/A4 radial-grid exact projection guards.
c["r25d_grid_projection_flag"]='MOBILEESS_R25D_RADIAL_GRID_PROJECTION' in mt
c["r25d_static_subtree_condensation"]='condense_static_subtree_flows' in mt and 'skeleton_balance_child_terms' in mt
c["r25d_voltage_affine_projection"]='build_voltage_affine_map' in mt and 'propagate_projected_voltage_bounds' in mt
c["r25d_constant_static_line_qcp_gate"]='static_line_thermal_checks' in mt
c["r25d_full_168_voltage_output_preserved"]='full 168-node planning-voltage output contract' in mt
c["r25d_root_du_aux_removed"]='root dU auxiliary too' in mt
c["r25d_runtime_audit_present"]='ConversationA_R25D_RADIAL_GRID_EXACT_PROJECTION_AUDIT.json' in mt
q=subprocess.run([sys.executable,str(R/"r25d_radial_projection_proof_test.py")],capture_output=True,text=True)
try:
 r25d_proof=json.loads(q.stdout)
except Exception:
 r25d_proof={}
c["r25d_radial_projection_proof_test"]=q.returncode==0 and bool(r25d_proof.get("PASS"))
c["r25d_actual_topology_168_100_68"]=bool(r25d_proof.get("actual_BUILD7AR2_topology",{}).get("node_count")==168 and r25d_proof.get("actual_BUILD7AR2_topology",{}).get("decision_skeleton_node_count")==100 and r25d_proof.get("actual_BUILD7AR2_topology",{}).get("static_node_count")==68)
c["r25d_expected_H54_reduction"]=bool(r25d_proof.get("H54_structural_reduction",{}).get("total_continuous_variables_removed_structural")==13122 and r25d_proof.get("H54_structural_reduction",{}).get("line_circle_QCP_constraints_removed_by_constant_precheck")==3510)

# R25E/A5 exact node-binary / continuous-arc integrality compression guards.
c["r25e_node_arc_flag"]='MOBILEESS_R25E_NODE_ARC_EXACT' in mt
c["r25e_move_continuous"]='vtype=GRB.CONTINUOUS,name="move"' in mt
c["r25e_node_binary"]='vtype=GRB.BINARY,name="occ"' in mt
c["r25e_parallel_transition_fail_closed"]='parallel mobility transition after A2' in mt
c["r25e_occ_flow_in"]='occ_in_' in mt and 'occ_out_' in mt
c["r25e_runtime_certificate"]='ConversationA_R25E_NODE_BINARY_CONTINUOUS_ARC_EXACTNESS_CERTIFICATE.json' in mt
c["r25e_persistent_static_context"]='MOBILEESS_R25E_PERSISTENT_STATIC_CONTEXT' in mt and 'persistent topology drift' in mt
c["r25e_no_full_cross_issue_model_reuse"]='full_cross_issue_Gurobi_model_reuse' in mt
q=subprocess.run([sys.executable,str(R/"r25e_node_arc_exact_proof_test.py")],capture_output=True,text=True)
try:
 r25e_proof=json.loads(q.stdout)
except Exception:
 r25e_proof={}
c["r25e_node_arc_proof_test"]=q.returncode==0 and bool(r25e_proof.get("PASS"))
c["r25e_issue152_integer_upper_bound_4611"]=int(r25e_proof.get("A5_total_integer_upper_bound_before_dynamic_job_binaries",-1))==4611
c["r25e_min_binary_reduction_gt95pct"]=float(r25e_proof.get("minimum_integer_reduction_fraction_vs_R24_estimate",0.0))>0.95

# BUILD7BR4 lineage guards retained only for scientific semantics that remain unchanged.
mt=(R/"main.py").read_text()
for token in ['econ_env=m.getMultiobjEnv(4)','econ_env.setParam("MIPGap",econ_gap)',
              '"MIPGap_service_objectives":0.0','"MIPGap_economic":econ_gap',
              'final_economic_target_mip_gap','"mip_gap":final_pass_gap']:
 c["br4_lineage_guard_"+token[:38]]=token in mt
c["generic_multiobj_mipgap_removed"]='"mip_gap":m.MIPGap' not in mt
# Model-level exact MIPGap remains zero; BR5 changes only Threads and final-pass strategy.
c["global_exact_gap_preserved"]='m.Params.MIPGap=0;m.Params.MIPGapAbs=0' in mt


# BUILD7BR5: BR4 actual-thread regression and verified global-8 policy.
pa=R/"embedded/BUILD7BR4_PASS_AUTHORITY.tar.gz"
pl=R/"embedded/BUILD7BR4_RUNTIME_LOG_AUTHORITY.txt"
c["br4_pass_sha"]=s(pa)=="d164d0349d998c88df43c6cf759ffa3f6c278e96f61b7e157a5176920a6aba47"
c["br4_log_sha"]=s(pl)=="cbc5a07c69ef9beccddac0c1ce5c834217ff0b53197a6c10e42974232b198ae6"
lt=pl.read_text(errors="ignore")
counts=[int(x) for x in re.findall(r"Thread count was (\d+)",lt)]
c["br4_actual_was_one_thread"]=len(counts)>=5 and counts[-1]==1
mt=(R/"main.py").read_text()
for token in ['MOBILEESS_GUROBI_THREADS','m.Params.Threads=threads_req','m.Params.InheritParams=1',
              'm.Params.MultiObjPre=2','econ_env.setParam("InheritParams",1)',
              'econ_env.setParam("Threads",threads_req)','econ_env.setParam("MIPGap",econ_gap)',
              'econ_env.setParam("MIPFocus",3)','thread_policy_verified']:
 c["br5_guard_"+token[:42]]=token in mt
c["br4_hardcoded_obj5_thread8_removed"]='econ_env.setParam("Threads",8)' not in mt


# BUILD7BR6 exact speed-domain guards and BR5 solve evidence.
pa=R/"embedded/BUILD7BR5_SOLVE_EVIDENCE.tar.gz";pl=R/"embedded/BUILD7BR5_RUNTIME_LOG_AUTHORITY.txt"
c["br5_solve_evidence_sha"]=s(pa)=="79145bab05c4deb99c08a9099096d665ab36a53bd6e40ff3b55f56d715bb9974"
c["br5_runtime_log_sha"]=s(pl)=="fb0c0c42c4f8de025d58164cdbb2d3ff4188cd3788e434cfafd78306893d9216"
lt=pl.read_text(errors="ignore")
c["br5_actual_8thread_solve_evidence"]=("Thread count: 8 physical cores, 16 logical processors, using up to 8 threads" in lt and "Thread count was 8 (of 16 available processors)" in lt and "gap 1.3788%" in lt)
mt=(R/"main.py").read_text()
for token in [
 'MOBILEESS_GUROBI_THREADS","14"','1<=threads_req<=16','m.Params.Method=root_method',
 'BUILD7BR6_EXACT_ROUTE_PRUNING_AUDIT.json','terminal_arrival_dominated','soc_upper_bound_infeasible',
 'BUILD7BR6_LEX_ZERO_CERT_AUDIT.json','LEX_ZERO_CERT_SINGLE_ECON','wait_theoretical_lb',
 'BUILD7BR6_WARMSTART_AUDIT.json','BUILD7BR4_PASS_AUTHORITY.tar.gz',
 'GRB.Callback.MESSAGE','GRB.Callback.MSG_STRING','thread_counts_message','BUILD7BR6_GUROBI_TERMINATION.json']:
 c["br6_guard_"+token[:44]]=token in mt
c["br6_no_immediate_logfile_thread_verifier"]='glog=(out/"GUROBI_BUILD7B_ISSUE113.log").read_text' not in mt
c["br6_no_constraint_relaxation_tokens"]=all(x in mt for x in ['FeasibilityTol=1e-9','IntFeasTol=1e-9','OptimalityTol=1e-9'])


# BUILD7BR7 exact-domain sparsification and true timing guards.
mt=(R/"main.py").read_text()
for token in ["mv_by_mid_h=defaultdict(list)","stay_by_mid_h=defaultdict(list)",
              "for sid in sorted(reachable[h])","if not active:continue",
              "workload_debt_identically_zero=True",
              'depart=gp.quicksum(float(moves[(h,slot)]["energy_kWh"])/_c5r4_energy_scale_kwh_per_model_unit*v for slot,v in mv_by_mid_h.get((mid,h),[]))',
              '_stage("GUROBI_OPTIMIZE_BEGIN"',"_RUNTIME_EVENTS",
              "BUILD7BR7_RUNTIME_TIMING_FINAL.json"]:
 c["br7_guard_"+token[:42]]=token in mt
c["old_all_service_stay_loop_removed"]='for sid in SERVICES:\\n    v=m.addVar(vtype=GRB.BINARY,name=f"stay_{mid}_{h}_{sid}")' not in mt


# BR7 supersedes the earlier BR1/BR3 direct mv-iteration guards with a stricter indexed domain.
mt=(R/"main.py").read_text()
c["new_3tuple_depflag_present"]='depflag=gp.quicksum(v for slot,v in mv_by_mid_h.get((mid,h),[]))' in mt
c["reachable_mv_depart_present"]='depart=gp.quicksum(float(moves[(h,slot)]["energy_kWh"])/_c5r4_energy_scale_kwh_per_model_unit*v for slot,v in mv_by_mid_h.get((mid,h),[]))' in mt


# BR8 exact hot-path regression.
pa=R/"embedded/BUILD7BR7_PASS_AUTHORITY.tar.gz"; pl=R/"embedded/BUILD7BR7_RUNTIME_LOG_AUTHORITY.txt"
c["br8_parent_result_sha"]=s(pa)=="854e9fe4ba35da5765bca884d633e886e29b4b17497be1821f3f4ac824c27548"
c["br8_parent_log_sha"]=s(pl)=="622d6b4b71f3fed91d3a79f0faff55d93ed1c312bbbfbd9c1e4a35585938e078"
mt=(R/"main.py").read_text()
c["br8_legacy_pandas_filter_removed"]='route_df[route_df["od_index"].astype(int)==od]' not in mt
c["br8_stable_grouping_present"]='cols=cols.sort_values(["od_index","rank"],kind="mergesort")' in mt
c["br8_issue113_route_regression_present"]='BR8 fast Pareto kernel changed issue113 route-domain counts' in mt
c["br8_state_domain_rescan_removed"]='state_domain=set(reachable[h])' not in mt
c["br8_static_rack_index_present"]='racks_by_idc=' in mt
c["br8_static_topology_order_present"]='nodes_topo=' in mt
q=subprocess.run([sys.executable,str(R/"pareto_kernel_equivalence_test.py")],capture_output=True,text=True)
c["br8_pareto_equivalence_test"]=q.returncode==0 and '"pass": true' in q.stdout.lower()


# BUILD7BR9 lossless cache/index guards.
mt=(R/"main.py").read_text()
c["br9_parent_run_sha"]=C["parent_BUILD7BR8_run_sha256"]=="5f3e616684698f4c257c4ed17ef911b1d4c4a915db993eea42da4c59dc6ea0a7"
c["br9_parent_result_sha"]=C["parent_BUILD7BR8_result_sha256"]=="7c6148b6f1bb35bf13860efdbdd9f6670744a845b3be8573d7afb2a4196438ed"
c["br9_parent_log_sha"]=C["parent_BUILD7BR8_log_sha256"]=="f1a852c2280cc6743d033d782413d2a1540548d7a3aa7748c113a5ce26f11cfb"
c["br9_pareto_cache_sha"]=s(R/"embedded/BUILD7BR9_PARETO_CACHE_ISSUE113.npz")=="74d0d063fc36e576138b09b7a1af6f0767db1e57139855134e1f55bfd9e90a80"
for token in ["_PERSIST={}","_npz_immutable","prepare_static_context","x_active_by_d_h=defaultdict(list)","F_by_t=defaultdict(list)","dispatch_by_h_sid=defaultdict(list)","price_factor=np.asarray([float(priceq[h])*DT/1000.0 for h in range(H)]","voltage_const={}","pareto_moves_cached","BUILD7BR9_GOLDEN_MODEL_EQUIVALENCE.json",'"fingerprint_hex":"0x24b788bc"',"BUILD7BR9_RUNTIME_STAGE_LIVE.json"]:
 c["br9_guard_"+token[:44]]=token in mt
c["br9_no_matrix_api"]="addMVar" not in mt and "addMConstr" not in mt
c["br9_obj5_gap_guarded"]="MOBILEESS_GUROBI_ECON_MIPGAP" in mt and "m.Params.MIPGap=econ_gap" in mt
c["br9_threads_unchanged"]='MOBILEESS_GUROBI_THREADS","14"' in mt
c["br7_guard_BUILD7BR7_RUNTIME_TIMING_FINAL.json"]="BUILD7BR9_RUNTIME_TIMING_FINAL.json" in mt

# R25G post-A6 exact branching/redundant-integrality acceleration guards.
mt=(R/"main.py").read_text()
c["r25g_flag"]='MOBILEESS_R25G_HYBRID_STAY_BINARY' in mt
c["r25g_stay_binary"]='stay_td=m.addVars(stay_keys,vtype=GRB.BINARY,name="stay") if r25g_hybrid_stay_binary' in mt
c["r25g_move_remains_continuous"]='mv_td=m.addVars(mv_keys,lb=0.0,ub=1.0,vtype=GRB.CONTINUOUS,name="move")' in mt
c["r25g_debt_stay_cover"]='r25g_debt_stay_cover_' in mt
c["r25g_soc_stay_cover"]='r25g_soc_stay_cover_' in mt
q=subprocess.run([sys.executable,str(R/"r25g_hybrid_stay_binary_proof_test.py")],capture_output=True,text=True)
c["r25g_exact_proof_test"]=q.returncode==0 and '"status": "PASS"' in q.stdout

# R25H/B1 certificate-focused search-policy guards (solver-search only).
mt=(R/"main.py").read_text()
c["r25h_b1_flag"]='MOBILEESS_R25H_B1_CERTIFICATE_FOCUS' in mt
c["r25h_b1_requires_r25g"]='R25H B1 certificate-focused search policy requires frozen R25G hybrid STAY-binary foundation' in mt
c["r25h_b1_mipfocus3"]='if r25h_b1_certificate_focus and int(issue)>113:' in mt and 'm.Params.MIPFocus=3' in mt
c["r25h_b1_no_improvestart"]='m.Params.ImproveStartGap=(0.0 if r25h_b1_certificate_focus else 0.032)' in mt and 'econ_env.setParam("ImproveStartGap",0.0)' in mt
c["r25h_b1_old_primal_focus_gated"]='int(issue)>113 and not r25h_b1_certificate_focus' in mt
c["r25h_b1_runtime_audit"]='ConversationA_R25H_B1_CERTIFICATE_SEARCH_POLICY.json' in mt
q=subprocess.run([sys.executable,str(R/"r25h_b1_certificate_policy_proof_test.py")],capture_output=True,text=True)
try:
 b1_proof=json.loads(q.stdout)
except Exception:
 b1_proof={}
c["r25h_b1_policy_proof_test"]=q.returncode==0 and b1_proof.get("status")=="PASS"

# R25I/B2 exact numerical re-scaling guards.  Scientific variables/interfaces remain
# frozen; only internal R25D branch-flow auxiliaries use MW/Mvar instead of kW/kvar.
mt=(R/"main.py").read_text()
c["r25i_b2_flag"]='MOBILEESS_R25I_B2_NUMERICAL_RESCALING' in mt
c["r25i_b2_requires_b1"]='R25I B2 exact numerical rescaling requires frozen R25H B1 certificate-focused foundation' in mt
c["r25i_b2_balance_scale"]='(ownP[n]+float(_cp))/_r25i_flow_scale_kw_per_model_unit' in mt
c["r25i_b2_voltage_scale"]='_r25i_voltage_flow_coeff=(0.002*_r25i_flow_scale_kw_per_model_unit)' in mt
c["r25i_b2_thermal_scale"]='float(ll)/_r25i_flow_scale_kw_per_model_unit' in mt
c["r25i_b2_runtime_audit"]='ConversationA_R25I_B2_EXACT_NUMERICAL_RESCALING_AUDIT.json' in mt
q=subprocess.run([sys.executable,str(R/"r25i_b2_numerical_rescaling_proof_test.py")],capture_output=True,text=True)
try:
 b2_proof=json.loads(q.stdout)
except Exception:
 b2_proof={}
c["r25i_b2_exact_proof_test"]=q.returncode==0 and b2_proof.get("status")=="PASS"
c["r25i_b2_actual_168_topology"]=b2_proof.get("actual_BUILD7AR2_coefficients",{}).get("node_count")==168
c["r25i_b2_known_grid_min_2e6"]=abs(float(b2_proof.get("actual_BUILD7AR2_coefficients",{}).get("b2_min_voltage_flow_coefficient",0.0))-2e-6)<1e-15
c["r25i_b2_no_long_solver"]=b2_proof.get("long_solver_run") is False


# R25J/B3 MIQCP kernel diagnostic-screen guards.
mt=(R/"main.py").read_text()
c["r25j_b3_miqcp_env"]='MOBILEESS_GUROBI_MIQCPMETHOD' in mt and '_miqcp_method not in (-1,0,1)' in mt
c["r25j_b3_dynamic_method"]='m.Params.MIQCPMethod=_miqcp_method' in mt
c["r25j_b3_runtime_audit"]='ConversationA_R25J_B3_MIQCP_KERNEL_SCREEN_AUDIT.json' in mt
c["r25j_b3_stop_before_commit"]='R25J_B3_DIAGNOSTIC_STOP_BEFORE_PHYSICAL_COMMIT' in mt and 'MOBILEESS_R25J_B3_SCREEN_ONLY' in mt
q=subprocess.run([sys.executable,str(R/"r25j_b3_miqcp_kernel_screen_proof_test.py")],capture_output=True,text=True)
try:
 b3_proof=json.loads(q.stdout)
except Exception:
 b3_proof={}
c["r25j_b3_static_proof_test"]=q.returncode==0 and b3_proof.get("status")=="PASS"

# R25K/B4 evidence-driven root/branch strengthening guards.
mt=(R/"main.py").read_text()
c["r25k_b4_flag"]='MOBILEESS_R25K_B4_ROOT_BRANCH_STRENGTHENING' in mt
c["r25k_b4_requires_b2"]='R25K B4 root/branch strengthening requires frozen R25I B2 numerical-rescaling foundation' in mt
c["r25k_b4_freeze_b3_auto"]='-1 if r25k_b4_root_branch_strengthening else 1' in mt
c["r25k_b4_cutpasses3"]='m.Params.CutPasses=3' in mt
c["r25k_b4_mode_symmetry"]='r25k_mode_transit_symmetry_' in mt and 'mode[(mid,h)]<=_active_stay' in mt
c["r25k_b4_dense_debt_cover"]='r25k_debt_stay_cover_dense_' in mt
c["r25k_b4_dense_soc_cover"]='r25k_soc_stay_cover_dense_' in mt
c["r25k_b4_prefix_cover"]='r25k_mobility_soc_prefix_cover_' in mt
c["r25k_b4_branch_priority"]='v.BranchPriority=30' in mt and 'v.BranchPriority=20' in mt and 'v.BranchPriority=5' in mt
c["r25k_b4_runtime_audit"]='ConversationA_R25K_B4_ROOT_BRANCH_STRENGTHENING_AUDIT.json' in mt
q=subprocess.run([sys.executable,str(R/"r25k_b4_root_branch_strengthening_proof_test.py")],capture_output=True,text=True)
try:
 b4_proof=json.loads(q.stdout)
except Exception:
 b4_proof={}
c["r25k_b4_exact_proof_test"]=q.returncode==0 and b4_proof.get("status")=="PASS"
c["r25k_b4_792_exact_rows_expected"]=b4_proof.get("expected_total_new_exact_rows")==792
c["r25k_b4_physical_set_preserved"]=b4_proof.get("scientific_physical_feasible_set_changed") is False

c={k:bool(v) for k,v in c.items()};c["PASS"]=all(c.values());
# R25M/B6 certified relax-and-price exact decomposition guards.
mt=(R/"main.py").read_text()
c["r25m_b6_flag"]='MOBILEESS_R25M_B6_EXACT_DECOMPOSITION' in mt
c["r25m_b6_runtime_call"]='certified_path_decomposition_solve' in mt
c["r25m_b6_global_bound_acceptance"]='full_all_column_relaxation_lower_bound' in mt and 'R25M B6 exact all-column/branch-price lower bound' in mt
c["r25m_b6_no_same_issue_start"]='posthoc_same_issue_MIP_start_used' in (R/"r25m_b6_exact_path_decomposition.py").read_text()
q=subprocess.run([sys.executable,str(R/"r25m_b6_exact_path_decomposition_proof_test.py")],capture_output=True,text=True)
try:b6p=json.loads(q.stdout)
except Exception:b6p={}
c["r25m_b6_exact_proof_test"]=q.returncode==0 and bool(b6p.get("PASS"))
c["r25m_b6_restricted_bound_not_authority"]=bool(b6p.get("heuristic_restricted_master_bound_authority") is False)


# R25M/B6R1 Gurobi solution-attribute lifecycle regression.
q=subprocess.run([sys.executable,str(R/"r25m_b6r1_objval_lifecycle_proof_test.py")],capture_output=True,text=True)
try:
 b6r1=json.loads(q.stdout)
except Exception:
 b6r1={}
c["r25m_b6r1_objval_lifecycle_proof"]=q.returncode==0 and b6r1.get("status")=="PASS"

# R25M/B6R2 batch-pricing and conservative numerical guard regression.
q=subprocess.run([sys.executable,str(R/"r25m_b6r2_batch_pricing_numerical_guard_proof_test.py")],capture_output=True,text=True)
try:
 b6r2=json.loads(q.stdout)
except Exception:
 b6r2={}
c["r25m_b6r2_batch_pricing_proof"]=q.returncode==0 and b6r2.get("status")=="PASS" and b6r2.get("kbest_k")==8
c["r25m_b6r2_guard_only_weakens_lb"]=bool(b6r2.get("lower_bound_guard_can_only_weaken_certificate") is True)
c["r25m_b6r2_observed_rc_mismatch_inside_guard"]=float(b6r2.get("observed_B6R1_rc_mismatch",1.0)) < float(b6r2.get("B6R2_rc_audit_tol",0.0))

# R25M/B6R3 exact node-repriced branch-and-price fallback.
q=subprocess.run([sys.executable,str(R/"r25m_b6r3_certified_branch_price_proof_test.py")],capture_output=True,text=True)
try:
 b6r3=json.loads(q.stdout)
except Exception:
 b6r3={}
c["r25m_b6r3_branch_price_proof"]=q.returncode==0 and b6r3.get("status")=="PASS" and b6r3.get("restricted_shortest_path_trials")==500
c["r25m_b6r3_node_partition_proof"]=b6r3.get("node_branch_partition_checks")==6
c["r25m_b6r3_certificate_pruning_math"]=b6r3.get("certificate_pruning_math")=="PASS"
# Recompute PASS after the B6/B6R1/B6R2 checks; earlier releases computed it before these late guards.
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)

# R25V causal rolling multi-start and exact-CG round-trip reduction.
for _n in ["r25v_causal_multistart_proof_test.py","r25v_native_multistart_smoke.py"]:
 ast.parse((R/_n).read_text());c["syntax_"+_n]=True
q=subprocess.run([sys.executable,str(R/"r25v_causal_multistart_proof_test.py")],capture_output=True,text=True)
try:
 r25v=json.loads(q.stdout)
except Exception:
 r25v={}
c["r25v_exact_safe_contract"]=q.returncode==0 and r25v.get("status")=="PASS" and all(r25v.get("checks",{}).values())
c["r25v_native_smoke_present"]=(R/"r25v_native_multistart_smoke.py").is_file()
c["r25w_thread_cap_not_exact_last_count"]=(
 "configured_thread_cap_verified" in mt and
 "observed_thread_counts_within_requested_cap" in mt and
 "max(actual_thread_counts)" in mt and
 "actual_thread_counts[-1]==threads_req" not in mt)
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)

# R25T/B6-C6 bounded primal phase plus original compact exact authority.
ast.parse((R/"r25t_global_bound_portfolio_proof_test.py").read_text())
q=subprocess.run([sys.executable,str(R/"r25t_global_bound_portfolio_proof_test.py")],capture_output=True,text=True)
try:
 r25t=json.loads(q.stdout)
except Exception:
 r25t={}
rtchecks=r25t.get("checks",{}) if isinstance(r25t,dict) else {}
c["r25t_global_bound_portfolio_proof"]=q.returncode==0 and r25t.get("PASS") is True
c["r25t_restricted_bound_not_authority"]=rtchecks.get("restricted_bound_never_promoted") is True
c["r25t_original_compact_bound_authority"]=rtchecks.get("compact_bound_is_global_authority") is True
c["r25t_combined_bound_safe"]=rtchecks.get("max_of_valid_lower_bounds_is_valid") is True and rtchecks.get("combined_bound_gap_is_monotone") is True
c["r25t_ac_qcp_unchanged"]=rtchecks.get("ac_qcp_not_changed") is True
q=subprocess.run([sys.executable,str(R/"r25t_gurobi_compact_authority_smoke.py")],capture_output=True,text=True)
try:
 r25t_smoke=json.loads(q.stdout[q.stdout.find("{"):])
except Exception:
 r25t_smoke={}
c["r25t_gurobi_compact_authority_smoke"]=q.returncode==0 and r25t_smoke.get("status")=="PASS" and r25t_smoke.get("fixed_continuous_qcp_optimal") is True
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)

# R25N/B6-C5R4 complete internal MW/MWh normalization, fixed-integer
# continuous-QCP polish, and removal of the ineffective fixed-dual prepass.
q=subprocess.run([sys.executable,str(R/"r25n_b6c5r4_numerical_conditioning_polish_proof_test.py")],capture_output=True,text=True)
try:
    b6c5r4=json.loads(q.stdout)
except Exception:
    b6c5r4={}
dm=(R/"r25m_b6_exact_path_decomposition.py").read_text();mt=(R/"main.py").read_text()
c["r25n_b6c5r4_equivalence_proof"]=q.returncode==0 and b6c5r4.get("PASS") is True and int(b6c5r4.get("equivalence_failures",1))==0
c["r25n_b6c5r4_complete_unit_flag"]='MOBILEESS_R25N_B6C5R4_COMPLETE_UNIT_NORMALIZATION' in mt
c["r25n_b6c5r4_external_units_preserved"]='_c5r4_power_scale_kw_per_model_unit*sum(' in mt and '_c5r4_energy_scale_kwh_per_model_unit*E[' in mt
c["r25n_b6c5r4_polish"]='MOBILEESS_R25N_B6C5R4_FIXED_INTEGER_QCP_POLISH' in dm and 'fixed_integer_continuous_qcp_polish' in dm
c["r25n_b6c5r4_fixed_dual_removed"]='MOBILEESS_R25N_B6C5R4_DISABLE_FIXED_DUAL_PREPASS' in dm and 'disabled_by_C5R4' in dm
c["r25n_b6c5r4_exact_child_authority_retained"]='exact_child_QCP_reoptimization_retained' in dm and 'child_pricing_closure_retained' in dm
c["r25o_b6c5r4r1_root_rc_retry"]='QCP dual/RC audit failed after BarQCPConvTol retries' in dm and 'reduced_cost_accounting_mismatch' in dm
c["r25o_b6c5r4r1_fresh_kkt_retry"]='m.reset()' in dm and 'nm.reset()' in dm
c["r25o_b6c5r4r1_child_scaling"]='nm.Params.NumericFocus=max(2' in dm and 'nm.Params.ScaleFlag=2' in dm
c["r25o_b6c5r4r1_child_rc_audit"]="dual_audit['rc_accounting_max_error']" in dm
c["r25p_unlimited_gurobi_time_policy"]="GRB.INFINITY if not math.isfinite" in dm and "unlimited_completion" in dm
c["r25p_unlimited_iteration_and_node_policy"]="itertools.count() if max_iter is None" in dm and "bp_node_limit is None" in dm
c["r25p_certificate_fail_closed"]="R25P B6 global 3% certificate not reached" in mt
c["r25p_projected_constant_voltage_extract"]="_r25p_solution_scalar" in mt
c["r25p_final_54_of_54_gate"]="PASS_R25R_STAGE1_54_OF_54_FINAL" in mt and "all_54_global_3pct_certificates_pass" in mt
q=subprocess.run([sys.executable,str(R/"r25p_stage1_unlimited_completion_proof_test.py")],capture_output=True,text=True)
try:r25p=json.loads(q.stdout)
except Exception:r25p={}
c["r25p_unlimited_completion_proof"]=q.returncode==0 and r25p.get("PASS") is True
q=subprocess.run([sys.executable,str(R/"r25q_numerical_envelope_resume_proof_test.py")],capture_output=True,text=True)
try:r25q=json.loads(q.stdout)
except Exception:r25q={}
c["r25q_numerical_envelope_resume_proof"]=q.returncode==0 and r25q.get("PASS") is True
c["r25q_stricter_qcp_recovery"]="min(p,1e-12)" in dm and "BarHomogeneous=1" in dm and ".Quad=1" in dm
c["r25q_measured_rc_safety"]="effective_rc_guard" in dm and "bounded_RC_envelope_rule" in dm
c["r25q_verified_resume"]="R25Q continuation requires a verified contiguous prefix" in mt
q=subprocess.run([sys.executable,str(R/"r25r_retained_optimal_dual_resume_proof_test.py")],capture_output=True,text=True)
try:r25r=json.loads(q.stdout)
except Exception:r25r={}
c["r25r_retained_optimal_dual_resume_proof"]=q.returncode==0 and r25r.get("PASS") is True
c["r25r_root_suboptimal_retry_fallback"]="best_bounded_root_candidate" in dm and "stricter_retry_nonoptimal" in dm
c["r25r_child_suboptimal_retry_fallback"]="best_bounded_child_candidate" in dm and "child_branch_from_saved_optimal" in dm
c["r25n_b6c5r4_no_scientific_change"]=b6c5r4.get("guards",{}).get("scientific_feasible_set_preserved") is True and b6c5r4.get("guards",{}).get("objective_preserved_by_coordinate_change") is True
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)

# R25M/B6R4 explicit continuous node relaxation + exact root reuse regression.
q=subprocess.run([sys.executable,str(R/"r25m_b6r4_relax_dual_root_reuse_proof_test.py")],capture_output=True,text=True)
try:
 b6r4=json.loads(q.stdout)
except Exception:
 b6r4={}
c["r25m_b6r4_relax_dual_root_reuse_proof"]=q.returncode==0 and b6r4.get("status")=="PASS"
c["r25m_b6r4_no_scientific_change"]=b6r4.get("scientific_feasible_set_changed") is False and b6r4.get("objective_changed") is False
c["r25m_b6r4_child_pricing_required"]=b6r4.get("branch_child_all_column_pricing_required") is True
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)


# R25M/B6-C1 pristine continuous certificate-authority lifecycle repair.
for _n in ["r25m_b6c1_continuous_authority_proof_test.py","r25m_b6c1_gurobi_dual_lifecycle_smoke.py"]:
 ast.parse((R/_n).read_text());c["syntax_"+_n]=True
q=subprocess.run([sys.executable,str(R/"r25m_b6c1_continuous_authority_proof_test.py")],capture_output=True,text=True)
try:
 b6c1=json.loads(q.stdout)
except Exception:
 b6c1={}
c["r25m_b6c1_continuous_authority_proof"]=q.returncode==0 and b6c1.get("status")=="PASS"
dm=(R/"r25m_b6_exact_path_decomposition.py").read_text()
c["r25m_b6c1_pristine_authority_before_primal"]="bp_continuous_authority=m.copy()" in dm and dm.find("bp_continuous_authority=m.copy()") < dm.find("for v,typ in original_nonmob_types:v.VType=typ")
c["r25m_b6c1_no_post_mip_relax"]="bp_base=m.relax()" not in dm
c["r25m_b6c1_child_dual_runtime_guards"]=all(x in dm for x in ["linear_dual_available","quadratic_dual_available","reduced_cost_available","QCPi",".Pi",".RC"])
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)

# R25M/B6-C2 global path cache + parent/child inheritance + child k-best batch pricing.
for _n in ["r25m_b6c2_global_cache_batch_pricing_proof_test.py"]:
 ast.parse((R/_n).read_text());c["syntax_"+_n]=True
q=subprocess.run([sys.executable,str(R/"r25m_b6c2_global_cache_batch_pricing_proof_test.py")],capture_output=True,text=True)
try:
 b6c2=json.loads(q.stdout)
except Exception:
 b6c2={}
dm=(R/"r25m_b6_exact_path_decomposition.py").read_text()
c["r25m_b6c2_exact_proof"]=q.returncode==0 and b6c2.get("status")=="PASS" and int(b6c2.get("restricted_kbest_mismatches",1))==0
c["r25m_b6c2_global_cache_present"]="global_path_cache={mid:{} for mid in mids}" in dm and "global_inherit" in dm
c["r25m_b6c2_sparse_column_cache"]="'coeffs':path_coeffs_named(mid,path)" in dm and "'objective':float(path_obj(mid,path))" in dm
c["r25m_b6c2_child_batch_pricing"]="MOBILEESS_R25M_B6C2_CHILD_PRICING_BATCH" in dm and "k_shortest_paths_with_node_restrictions" in dm and "pricing_batch" in dm
c["r25m_b6c2_exact_min_closure_oracle"]=("Exact minimum path remains the scientific closure oracle" in dm or "Exact TRUE-dual shortest path remains the closure oracle" in dm or "Exact TRUE-dual minimum path remains the scientific closure oracle" in dm)
c["r25m_b6c2_no_scientific_change"]=b6c2.get("scientific_feasible_set_changed") is False and b6c2.get("objective_changed") is False
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)

# R25M/B6-C3 true-dual-certified dual stabilization.
for _n in ["r25m_b6c3_dual_stabilization_proof_test.py"]:
 ast.parse((R/_n).read_text());c["syntax_"+_n]=True
q=subprocess.run([sys.executable,str(R/"r25m_b6c3_dual_stabilization_proof_test.py")],capture_output=True,text=True)
try:
 b6c3=json.loads(q.stdout)
except Exception:
 b6c3={}
dm=(R/"r25m_b6_exact_path_decomposition.py").read_text()
c["r25m_b6c3_exactness_proof"]=q.returncode==0 and b6c3.get("status")=="PASS" and int(b6c3.get("false_pricing_closure_cases",1))==0 and int(b6c3.get("unsafe_stabilized_insertions",1))==0
c["r25m_b6c3_stabilized_candidate_generation"]=all(x in dm for x in ["MOBILEESS_R25M_B6C3_DUAL_STABILIZATION","blend_dual_maps","pricing_stabilized_true_rc_filtered"])
c["r25m_b6c3_true_dual_filter"]="true_reduced_cost_for_path" in dm and "true_rc < -pricing_tol" in dm
c["r25m_b6c3_true_dual_closure_oracle"]="Exact TRUE-dual shortest path remains the closure oracle" in dm and "all(v>=-effective_rc_guard for v in mins.values())" in dm
c["r25m_b6c3_stabilized_dual_not_authority"]=b6c3.get("stabilized_dual_certificate_authority") is False
c["r25m_b6c3_no_scientific_change"]=b6c3.get("scientific_feasible_set_changed") is False and b6c3.get("objective_changed") is False
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")


# R25M/B6-C4 reliability strong branching (selection-only; exact child pricing remains authority).
q=subprocess.run([sys.executable,str(R/"r25m_b6c4_strong_branching_proof_test.py")],capture_output=True,text=True)
try:
 b6c4=json.loads(q.stdout)
except Exception:
 b6c4={}
dm=(R/"r25m_b6_exact_path_decomposition.py").read_text()
c["r25m_b6c4_exact_partition_proof"]=q.returncode==0 and b6c4.get("status")=="PASS" and int(b6c4.get("mobility_branch_partition_failures",1))==0
c["r25m_b6c4_strong_branch_controls"]=all(x in dm for x in ["MOBILEESS_R25M_B6C4_STRONG_BRANCHING","MOBILEESS_R25M_B6C4_STRONG_CANDIDATES","MOBILEESS_R25M_B6C4_PROBE_TIMELIMIT","MOBILEESS_R25M_B6C4_PSEUDOCOST_RELIABILITY"])
c["r25m_b6c4_selection_only_not_authority"]="certificate_authority':False" in dm and b6c4.get("strong_branch_probe_certificate_authority") is False
c["r25m_b6c4_exact_child_pricing_preserved"]="exact_child_pricing_still_required':True" in dm and b6c4.get("exact_child_pricing_closure_still_required") is True
c["r25m_b6c4_late_fractionality_rule_removed"]="late_horizon_fractionality_only_rule_removed':True" in dm and b6c4.get("late_horizon_fractionality_only_rule_removed") is True
c["r25m_b6c4_pseudocost_runtime_update"]="_record_exact_child_pseudocost" in dm and "_pseudocost_prediction" in dm
c["r25m_b6c4_no_scientific_change"]=b6c4.get("scientific_feasible_set_changed") is False and b6c4.get("objective_changed") is False
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")

print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)


# R25N/B6-C5R1 gap authority / target certificate regression.
for _n in ["r25n_b6c5r1_gap_authority_target_certificate_proof_test.py"]:
 ast.parse((R/_n).read_text());c["syntax_"+_n]=True
q=subprocess.run([sys.executable,str(R/"r25n_b6c5r1_gap_authority_target_certificate_proof_test.py")],capture_output=True,text=True)
try:
 b6c5r1=json.loads(q.stdout)
except Exception:
 b6c5r1={}
dm=(R/"r25m_b6_exact_path_decomposition.py").read_text();mt=(R/"main.py").read_text()
_cc=b6c5r1.get("checks",{}) if isinstance(b6c5r1,dict) else {}
c["r25n_b6c5r1_gap_proof"]=q.returncode==0 and b6c5r1.get("PASS") is True and int(_cc.get("gap_threshold_equivalence_cases",0))==10000 and int(_cc.get("fixed_dual_child_bound_random_objectives",0))==40000
c["r25n_b6c5r1_explicit_3pct"]='Stage-1 gap target must equal 0.03 exactly' in mt
c["r25n_b6c5r1_certificate_lb_audit"]='certificate_lower_bound_authority' in mt and 'restricted_master_native_mip_gap_is_global_authority' in mt
c["r25n_b6c5r1_restricted_infeasible_failclosed"]='restricted_rmp_infeasible_requires_phase1_pricing' in dm
c["r25n_b6c5r1_unresolved_ancestor_bound"]='conservative ancestor LBs for unresolved children' in dm
c["r25n_b6c5r1_fixed_dual_prepass"]='ROOT_TRUE_DUAL_PLUS_EXACT_RESTRICTED_DAG_MIN_RC_WITH_CONVEXITY_DUAL_SHIFT' in dm
c["r25n_b6c5r1_monotone_child_lb"]="lb=max(float(plb),float(rr['lb']))" in dm
c["r25n_b6c5r1_route_tiebreak_semantics"]='procurement_only_relative_gap_not_separately_certified' in mt
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)

# R25N/B6-C5R3 final algorithm correction: Threads=4 winner, mobility-first
# exact branching, and fixed-dual multiway time-layer partition.
for _n in ["r25n_b6c5r3_final_algorithm_correction_proof_test.py"]:
    ast.parse((R/_n).read_text());c["syntax_"+_n]=True
q=subprocess.run([sys.executable,str(R/"r25n_b6c5r3_final_algorithm_correction_proof_test.py")],capture_output=True,text=True)
try:
    b6c5r3=json.loads(q.stdout)
except Exception:
    b6c5r3={}
dm=(R/"r25m_b6_exact_path_decomposition.py").read_text()
_cc=b6c5r3.get("checks",{}) if isinstance(b6c5r3,dict) else {}
c["r25n_b6c5r3_multiway_partition_proof"]=q.returncode==0 and b6c5r3.get("PASS") is True and int(_cc.get("multiway_partition_failures",1))==0
c["r25n_b6c5r3_mobility_first"]="MOBILEESS_R25N_B6C5R3_MOBILITY_FIRST" in dm and "mobility_integrality_first" in dm
c["r25n_b6c5r3_fixed_dual_multiway"]="MOBILEESS_R25N_B6C5R3_FIXED_DUAL_MULTIWAY" in dm and "mobility_time_multi" in dm
c["r25n_b6c5r3_primal_heuristics"]="MOBILEESS_R25N_B6C5R3_PRIMAL_HEURISTICS" in dm
c["r25n_b6c5r3_exact_authority_preserved"]="ROOT_TRUE_DUAL_PLUS_EXACT_RESTRICTED_DAG_MIN_RC_WITH_CONVEXITY_DUAL_SHIFT" in dm
c["r25n_b6c5r3_no_scientific_change"]=b6c5r3.get("checks",{}).get("scientific_feasible_set_changed") is False and b6c5r3.get("checks",{}).get("objective_changed") is False
c["PASS"]=all(bool(v) for k,v in c.items() if k!="PASS")
print(json.dumps(c,indent=2,sort_keys=True))
if not c["PASS"]:raise SystemExit(2)
