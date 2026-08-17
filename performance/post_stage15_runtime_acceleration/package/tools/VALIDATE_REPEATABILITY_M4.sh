#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/jaewon/miniconda3/envs/power_v61/bin/python
REPO=/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration
SRC=/home/jaewon/mobile_ess_work/frozen_artifacts/B_FIRST6_REP_WEEKS_ACTUAL_CURRENT/W02_2025-01-13/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION
DST=/home/jaewon/mobile_ess_work/frozen_artifacts/PRE_W02_REPEATABILITY_M4_CURRENT
ISSUE=3517
if [[ -e "$DST" ]]; then
 mv "$DST" "${DST}_ARCHIVE_$(date -u +%Y%m%dT%H%M%SZ)"
fi
cp -al "$SRC" "$DST"
mkdir -p "$DST/interrupted_attempts/repeatability_removed"
mv "$DST/engine/issue_003517" "$DST/interrupted_attempts/repeatability_removed/"
mapfile -t groups < <("$PY" "$HERE/tools/CPU_AFFINITY_4X4.py" --plain)
taskset -c "${groups[3]}" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" --repo "$REPO" \
 --config "$HERE/configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json" --output "$DST" \
 --candidate-id W02_2025-01-13 --benchmark-issues 62 >"$DST/REPEATABILITY_RERUN.log" 2>&1
"$PY" -c 'import csv,hashlib,json,sys; from pathlib import Path
src,dst,out=map(Path,sys.argv[1:]); a=src/"engine/issue_003517"; b=dst/"engine/issue_003517"; exact=["BUILD7C_PRECOMMIT_STATE.json","BUILD7C_POSTCOMMIT_STATE.json","BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json","BUILD7B_FULL54_JOB_PLAN.csv","BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"]
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); rows={f:{"original":h(a/f),"repeat":h(b/f)} for f in exact}; byte_pass=all(v["original"]==v["repeat"] for v in rows.values())
def action(p):
 r=[x for x in csv.DictReader(open(p,encoding="utf-8-sig")) if int(float(x["horizon_step"]))==0]; out=[]
 for x in r:
  z={k:x[k] for k in ("mess_id","state","service_id")}
  for k in ("P_discharge_kW","P_charge_kW","Q_kvar","SOC_kWh"):
   v=float(x[k]);z[k]=0.0 if abs(v)<5e-4 else round(v,3)
  out.append(z)
 return out
aa=action(a/"BUILD7B_FULL54_MESS_PLAN.csv");bb=action(b/"BUILD7B_FULL54_MESS_PLAN.csv"); canon=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest(); action_pass=aa==bb
ea=json.load(open(a/"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_3517.json"));eb=json.load(open(b/"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_3517.json")); tolerances={"voltage_min_pu":1e-6,"voltage_max_pu":1e-6,"line_max_loading_pu":1e-6,"transformer_max_kva_loading_pu":1e-6,"transformer_max_current_loading_pu":1e-6,"root_import_p_kw":1e-2,"root_import_q_kvar":1e-2}; deltas={k:abs(float(ea[k])-float(eb[k])) for k in tolerances}; ac_pass=ea["converged"]==eb["converged"]==True and ea["hard_constraint_pass"]==eb["hard_constraint_pass"]==True and all(deltas[k]<=tolerances[k] for k in tolerances)
ok=byte_pass and action_pass and ac_pass;x={"schema_version":"mobileess.pre_w02.repeatability.v2","status":"PASS" if ok else "FAIL_CLOSED","byte_exact_committed_state_and_discrete_action_files":rows,"byte_exact_pass":byte_pass,"canonical_h0_action_sha256":{"original":canon(aa),"repeat":canon(bb)},"canonical_h0_action_resolution":"1e-3 kW/kvar/kWh with values below 5e-4 normalized to zero","canonical_h0_action_pass":action_pass,"fresh_exact_ac_repeatability":{"pass":ac_pass,"absolute_tolerances":tolerances,"absolute_deltas":deltas,"same_hard_gate_classification":ea["hard_constraint_pass"]==eb["hard_constraint_pass"]},"H1_H53_nonbinding_guidance_excluded":True,"deterministic_h0_tiebreak":True,"test_only_bounded":True,"full_W02_executed":False}; out.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n");sys.exit(0 if ok else 2)' \
 "$SRC" "$DST" "$DST/PRE_W02_REPEATABILITY_EVIDENCE.json"
echo PRE_W02_REPEATABILITY_STATUS=PASS
