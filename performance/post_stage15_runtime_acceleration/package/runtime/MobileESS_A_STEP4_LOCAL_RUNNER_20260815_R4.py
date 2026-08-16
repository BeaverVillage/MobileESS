#!/usr/bin/env python3
"""Conversation A 단계 4 R4: shifted-active-plan causal replay/invalidation gate.

Correct R26 semantics:
- Initialize one valid slow Route/Work plan at issue 113.
- At every committed five-minute boundary, shift that same active plan by one step.
- Rebuild the current causal model using only current observations/forecasts.
- Bind the shifted active slow plan if it remains admissible.
- If current causal information invalidates the shifted plan, stop BEFORE solve/commit
  and emit a structured replan-required event. This is a PASS for 단계 4 because
  event-triggered invalidation is the intended R26 behavior.
- Never borrow the next issue's Stage-1 exact plan: after fast h0 reoptimization the
  physical PRE state is no longer the Stage-1 exact trajectory.

단계 4 therefore validates either:
  A) shifted active plan remains valid through all 54 issues, or
  B) the first invalidation is detected fail-closed at an issue boundary with an
     explicit affected MESS/job scope for 단계 5/6.

No online global 3% certificate is claimed.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import time
import traceback
from typing import Any, Mapping

import pandas as pd


def _read_plan_csv(path:Path)->pd.DataFrame:
    """Read a plan table while preserving the frozen zero-byte empty-set form."""
    return pd.DataFrame() if path.stat().st_size == 0 else pd.read_csv(path)

HERE=Path(__file__).resolve().parent
BASE_RUNNER=HERE/"MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2.py"
if not BASE_RUNNER.is_file():
    raise SystemExit(f"Missing companion file: {BASE_RUNNER}")
spec=importlib.util.spec_from_file_location("a_step2_base",BASE_RUNNER)
if spec is None or spec.loader is None:
    raise SystemExit("Unable to import 단계 2~3 companion runner")
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)


class PlanInvalidation(BaseException):
    def __init__(
        self,
        *,
        issue:int,
        reasons:list[str],
        affected_mess_ids:list[str]|None=None,
        affected_job_ids:list[str]|None=None,
        detail:Mapping[str,Any]|None=None,
    ):
        super().__init__("; ".join(reasons))
        self.issue=int(issue)
        self.reasons=tuple(sorted(set(map(str,reasons))))
        self.affected_mess_ids=tuple(sorted(set(map(str,affected_mess_ids or []))))
        self.affected_job_ids=tuple(sorted(set(map(str,affected_job_ids or []))))
        self.detail=dict(detail or {})


def find_json_in_tar(archive:Path,basename:str)->dict[str,Any]:
    with tarfile.open(archive,"r:gz") as tf:
        hits=[m for m in tf.getmembers() if m.isfile() and Path(m.name).name==basename]
        if len(hits)!=1:
            raise RuntimeError(f"{archive}: expected one {basename}, found {len(hits)}")
        fh=tf.extractfile(hits[0])
        if fh is None: raise RuntimeError(f"Cannot read {basename}")
        obj=json.loads(fh.read().decode("utf-8"))
        if not isinstance(obj,dict): raise RuntimeError(f"{basename} not JSON object")
        return obj


def validate_step2_archive(path:Path)->dict[str,Any]:
    if not path.is_file(): raise FileNotFoundError(path)
    result=find_json_in_tar(path,"A_STEP2_3_RESULT.json")
    if result.get("step2")!="PASS" or result.get("step3")!="PASS":
        raise RuntimeError(f"단계 2~3 prerequisite did not PASS: {result}")
    return {"path":str(path),"sha256":base.sha256(path),"result":result}


def _tail_extend_mess(previous:pd.DataFrame)->pd.DataFrame:
    """Shift h=1..53 to h=0..52 and append causal STAY at new h=53.

    Frozen planner construction forbids selected MOVE arrival at or beyond H, so
    every valid full-H plan must have a stationary terminal row. Fail closed if
    the actual prior solved plan violates that contract.
    """
    rows=[]
    for mid,g in previous.groupby("mess_id",sort=True):
        g=g.sort_values("horizon_step")
        tail=g[g["horizon_step"].astype(int)==53]
        if len(tail)!=1:
            raise RuntimeError(f"{mid}: prior plan missing unique terminal h53 row")
        t=tail.iloc[0].to_dict()
        if str(t["state"])!="STAY" or pd.isna(t["service_id"]):
            raise RuntimeError(f"{mid}: terminal plan is not stationary; explicit tail policy required")
        shifted=g[g["horizon_step"].astype(int)>=1].copy()
        shifted["horizon_step"]=shifted["horizon_step"].astype(int)-1
        rows.extend(shifted.to_dict("records"))
        new=dict(t)
        new["horizon_step"]=53
        new["state"]="STAY"
        new["service_id"]=str(t["service_id"])
        for col in ("P_discharge_kW","P_charge_kW","Q_kvar"):
            if col in new: new[col]=0.0
        rows.append(new)
    out=pd.DataFrame(rows)
    if len(out)!=len(previous):
        raise RuntimeError(f"shifted MESS plan row count drift {len(out)} != {len(previous)}")
    return out.sort_values(["mess_id","horizon_step"],kind="mergesort").reset_index(drop=True)


def shifted_reference_from_previous(issue:int,engine:Path)->dict[str,Any]:
    prev=engine/f"issue_{issue-1:06d}"
    job_path=prev/"BUILD7B_FULL54_JOB_PLAN.csv"
    mess_path=prev/"BUILD7B_FULL54_MESS_PLAN.csv"
    move_path=prev/"BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"
    post_path=prev/"BUILD7C_POSTCOMMIT_STATE.json"
    for p in (job_path,mess_path,move_path,post_path):
        if not p.is_file(): raise RuntimeError(f"previous committed plan artifact missing: {p}")
    jobs=_read_plan_csv(job_path)
    # Work starts at issue-1 were physically committed and must disappear from the active plan.
    if len(jobs):
        jobs=jobs[jobs["start_step"].astype(int)>=int(issue)].copy().reset_index(drop=True)
    mess=_tail_extend_mess(_read_plan_csv(mess_path))
    moves=_read_plan_csv(move_path)
    if len(moves):
        moves=moves[moves["horizon_step"].astype(int)>=1].copy()
        moves["horizon_step"]=moves["horizon_step"].astype(int)-1
        # departure_step is absolute and therefore remains unchanged.
        moves=moves.reset_index(drop=True)
    post=json.loads(post_path.read_text())
    return {
        "BUILD7B_FULL54_JOB_PLAN.csv":jobs,
        "BUILD7B_FULL54_MESS_PLAN.csv":mess,
        "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv":moves,
        "active_plan_parent_issue":issue-1,
        "active_plan_source_post_sha256":str(post["sha256"]),
        "authority":"SHIFTED_PREVIOUS_CAUSAL_ACTIVE_PLAN",
    }


def current_reference(issue:int,repo:Path,temp:Path,engine:Path)->dict[str,Any]:
    if issue==113:
        ref=base.load_issue113_reference(repo,temp)
        ref["authority"]="FROZEN_ISSUE113_INITIAL_ACTIVE_PLAN"
        ref["active_plan_parent_issue"]=None
        return ref
    return shifted_reference_from_previous(issue,engine)


def bind_shifted_active_plan(loc:Mapping[str,Any],ref:Mapping[str,Any],issue:int)->dict[str,Any]:
    """Bind the current active slow plan and classify invalidation before optimize."""
    x=loc["x"];defer=loc["defer"];stay=loc["stay"];mv=loc["mv"]
    node_occ=loc.get("node_occ",{});moves=loc["moves"];model=loc["m"]

    job_df=ref["BUILD7B_FULL54_JOB_PLAN.csv"]
    mess_df=ref["BUILD7B_FULL54_MESS_PLAN.csv"]
    move_df=ref["BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"]
    fixed_location=bool(ref.get("fixed_location_projection",False))
    if fixed_location and not bool(loc.get("fixed_location_projection",False)):
        raise RuntimeError("M4 reference/model fixed-location projection mismatch")
    active_projection=bool(loc.get("active_plan_mobility_projection",False))

    selected_x={
        (str(r.job_uid),str(r.destination_IDC_id),str(r.rack_pool_id),int(r.start_step))
        for r in job_df.itertuples(index=False)
    }
    missing_x=sorted(selected_x-set(x))
    if missing_x:
        raise PlanInvalidation(
            issue=issue,
            reasons=["PLANNED_WORK_ASSIGNMENT_NO_LONGER_ADMISSIBLE"],
            affected_job_ids=[k[0] for k in missing_x],
            detail={"missing_job_choices":missing_x[:30]},
        )

    selected_jobs={k[0] for k in selected_x}
    model_jobs=sorted({str(k[0]) for k in x})
    urgent_unplanned=sorted(j for j in model_jobs if j not in selected_jobs and j not in {str(k) for k in defer})
    if urgent_unplanned:
        raise PlanInvalidation(
            issue=issue,
            reasons=["NEW_OR_UNPLANNED_JOB_REQUIRES_DISCRETE_START_WITHIN_HORIZON"],
            affected_job_ids=urgent_unplanned,
            detail={"urgent_unplanned_jobs":urgent_unplanned[:100]},
        )

    selected_mv={
        (str(r.mess_id),int(r.horizon_step),int(r.slot))
        for r in move_df.itertuples(index=False)
    }
    missing_mv=[] if active_projection else sorted(selected_mv-set(mv))
    if missing_mv:
        raise PlanInvalidation(
            issue=issue,
            reasons=["SHIFTED_MOBILITY_MOVE_NO_LONGER_ADMISSIBLE_UNDER_CURRENT_CAUSAL_STATE_FORECAST"],
            affected_mess_ids=[k[0] for k in missing_mv],
            detail={"missing_move_choices":missing_mv[:50]},
        )

    selected_stay={
        (str(r.mess_id),int(r.horizon_step),str(r.service_id))
        for r in mess_df.itertuples(index=False) if str(r.state)=="STAY"
    }
    if fixed_location:
        homes={str(k):str(v) for k,v in dict(ref.get("fixed_location_homes",{})).items()}
        if set(homes)!={f"MESS{i:02d}" for i in range(1,5)} or len(set(homes.values()))!=4:
            raise RuntimeError(f"M4 active-plan reference has invalid fixed-site authority: {homes}")
        expected={(mid,h,sid) for mid,sid in homes.items() for h in range(54)}
        if selected_stay!=expected or selected_mv:
            raise RuntimeError("M4 active plan is not the exact selected-PCC stationary projection")
        missing_stay=[]
    elif active_projection:
        missing_stay=[]
    else:
        missing_stay=sorted(selected_stay-set(stay))
    if missing_stay:
        raise PlanInvalidation(
            issue=issue,
            reasons=["SHIFTED_STAY_STATE_NO_LONGER_REACHABLE"],
            affected_mess_ids=[k[0] for k in missing_stay],
            detail={"missing_stay_choices":missing_stay[:50]},
        )

    selected_occ=set()
    for mid,h,sid in selected_stay:
        selected_occ.add((mid,h,sid));selected_occ.add((mid,h+1,sid))
    for mid,h,slot in selected_mv:
        mm=moves[(h,slot)]
        selected_occ.add((mid,h,str(mm["source"])))
        selected_occ.add((mid,h+int(mm["D"]),str(mm["dest"])))
    if node_occ:
        missing_occ=sorted(selected_occ-set(node_occ))
        if missing_occ:
            raise PlanInvalidation(
                issue=issue,
                reasons=["SHIFTED_OCCUPANCY_STATE_NO_LONGER_ADMISSIBLE"],
                affected_mess_ids=[k[0] for k in missing_occ],
                detail={"missing_occupancy":missing_occ[:50]},
            )

    # Only after all semantic admissibility gates pass do we mutate variable bounds.
    for key,var in x.items():
        base._set_fixed(var,1.0 if key in selected_x else 0.0)
    for uid,var in defer.items():
        base._set_fixed(var,0.0 if str(uid) in selected_jobs else 1.0)
    for key,var in mv.items():
        base._set_fixed(var,1.0 if key in selected_mv else 0.0)
    for key,var in stay.items():
        base._set_fixed(var,1.0 if key in selected_stay else 0.0)
    if node_occ:
        for key,var in node_occ.items():
            base._set_fixed(var,1.0 if key in selected_occ else 0.0)

    model.update()
    int_names=[
        str(v.VarName) for v in model.getVars()
        if str(v.VType).upper() in {"B","I","S","N"} and float(v.UB)-float(v.LB)>1e-12
    ]
    unexpected=[n for n in int_names if not n.startswith("mode_")]
    if unexpected:
        raise RuntimeError(f"Residual non-mode integer vars after active-plan binding: {unexpected[:30]}")
    return {
        "authority":ref.get("authority"),
        "active_plan_parent_issue":ref.get("active_plan_parent_issue"),
        "active_plan_source_post_sha256":ref.get("active_plan_source_post_sha256"),
        "selected_job_choices":len(selected_x),
        "unplanned_deferrable_jobs":len([j for j in model_jobs if j not in selected_jobs]),
        "selected_move":len(selected_mv),
        "selected_stay":len(selected_stay),
        "selected_occupancy":len(selected_occ),
        "fixed_location_projection":fixed_location,
        "active_plan_mobility_projection":active_projection,
        "fixed_job_choice_variables":len(x),
        "fixed_defer_variables":len(defer),
        "fixed_move_variables":len(mv),
        "fixed_stay_variables":len(stay),
        "fixed_occupancy_variables":len(node_occ),
        "residual_integer_count":len(int_names),
        "residual_integer_family":"FAST_DISPATCH_MODE_ONLY",
        "future_actual_used":False,
    }


def validate_previous_post_is_current_pre(issue:int,issue_out:Path,engine:Path)->None:
    if issue<=113:return
    prev=json.loads((engine/f"issue_{issue-1:06d}/BUILD7C_POSTCOMMIT_STATE.json").read_text())
    cur=json.loads((issue_out/"BUILD7C_PRECOMMIT_STATE.json").read_text())
    if str(prev["sha256"])!=str(cur["sha256"]):
        raise RuntimeError(
            f"causal PRE/POST chain break issue={issue}: prevPOST={prev['sha256']} currentPRE={cur['sha256']}"
        )


def run(args:argparse.Namespace)->int:
    repo=base.locate_repo(args.repo)
    work=Path.home()/"mobile_ess_work"
    base.assert_no_active_r25t(work)
    lock=base.acquire_stage2_lock(work)
    tag=base.now_tag()
    run_root=base.SCRATCH_ROOT/f"A_STEP4_{tag}"
    run_root.mkdir(parents=True,exist_ok=False)
    log_dir=base.LOG_ROOT/run_root.name;log_dir.mkdir(parents=True,exist_ok=False)
    console=log_dir/"RUN_CONSOLE.log"
    rc=2

    with console.open("w",encoding="utf-8",buffering=1) as lh:
        oldo,olde=sys.stdout,sys.stderr
        sys.stdout=base.Tee(oldo,lh);sys.stderr=base.Tee(olde,lh)
        try:
            prereq=validate_step2_archive(Path(args.stage2_result))
            base.write_json(run_root/"00_STEP2_3_PREREQUISITE.json",prereq)
            auth=base.assert_source_authority(repo);base.write_json(run_root/"01_SOURCE_AUTHORITY.json",auth)
            deps=base.dependency_preflight();base.write_json(run_root/"02_DEPENDENCY_PREFLIGHT.json",deps)

            sm=base.load_science(repo)
            original_jw=sm.jw
            issue_t0:dict[int,float]={};issue_wall:dict[int,float]={}
            solver_rows:list[dict[str,Any]]=[]
            temp_ref=run_root/"reference_temp";temp_ref.mkdir()
            engine=run_root/"engine";engine.mkdir()
            invalidation:PlanInvalidation|None=None

            def jw_wrapper(path:Any,value:Any):
                out=original_jw(path,value)
                try:
                    pp=Path(path)
                    if pp.parent.name.startswith("issue_"):
                        issue=int(pp.parent.name.split("_")[-1])
                        if pp.name=="BUILD7C_PRECOMMIT_STATE.json":
                            issue_t0[issue]=time.monotonic()
                        elif pp.name=="BUILD7C_POSTCOMMIT_STATE.json" and issue in issue_t0:
                            issue_wall[issue]=time.monotonic()-issue_t0[issue]
                except Exception: pass
                return out

            def conditioned_decomp(**kwargs:Any):
                import inspect
                import gurobipy as gp
                fr=inspect.currentframe();assert fr is not None and fr.f_back is not None
                loc=fr.f_back.f_locals
                issue=int(loc["issue"]);model=kwargs["m"];issue_out=Path(loc["out"])
                validate_previous_post_is_current_pre(issue,issue_out,engine)
                ref=current_reference(issue,repo,temp_ref,engine)
                bind=bind_shifted_active_plan(loc,ref,issue)
                base.write_json(issue_out/"R26_STEP4_ACTIVE_PLAN_BINDING_AUDIT.json",{"issue":issue,**bind})

                model.Params.Threads=4
                model.Params.TimeLimit=float(args.fast_limit_seconds)
                model.Params.MIPGap=0.03
                model.Params.MIPFocus=1
                model.Params.OutputFlag=1
                model.update()
                ints=[
                    str(v.VarName) for v in model.getVars()
                    if str(v.VType).upper() in {"B","I","S","N"} and float(v.UB)-float(v.LB)>1e-12
                ]
                bad=[n for n in ints if not n.startswith("mode_")]
                if bad: raise RuntimeError(f"issue {issue}: unexpected residual integer vars {bad[:30]}")

                t0=time.monotonic()
                cb=kwargs.get("base_callback")
                model.optimize(cb) if cb is not None else model.optimize()
                primary_wall=time.monotonic()-t0
                primary=base.solver_quality(model)
                if int(model.SolCount)<1:
                    raise PlanInvalidation(
                        issue=issue,
                        reasons=["SHIFTED_ACTIVE_PLAN_CONDITIONED_DISPATCH_INFEASIBLE"],
                        affected_mess_ids=sorted(str(x) for x in loc.get("mids",[])),
                        affected_job_ids=sorted(str(x) for x in loc.get("jobs",[])),
                        detail={"solver":primary},
                    )

                polish=None
                need=int(model.Status)!=int(gp.GRB.OPTIMAL)
                try: need=need and float(model.MIPGap)>0.03+1e-12
                except Exception: pass
                if need:
                    for v in loc["mode"].values():
                        base._set_fixed(v,1.0 if float(v.X)>=0.5 else 0.0)
                    model.update();model.reset()
                    model.Params.TimeLimit=max(30.0,float(args.fast_limit_seconds)-primary_wall)
                    pt=time.monotonic();model.optimize();pw=time.monotonic()-pt
                    polish=base.solver_quality(model);polish["wall_seconds"]=pw
                    if int(model.Status)!=int(gp.GRB.OPTIMAL):
                        raise PlanInvalidation(
                            issue=issue,
                            reasons=["SHIFTED_ACTIVE_PLAN_FIXED_MODE_QCP_INFEASIBLE"],
                            affected_mess_ids=sorted(str(x) for x in loc.get("mids",[])),
                            detail={"primary":primary,"polish":polish},
                        )

                total=time.monotonic()-t0
                q=base.solver_quality(model);q.update({
                    "issue":issue,
                    "solver_wall_seconds":total,
                    "primary_wall_seconds":primary_wall,
                    "primary":primary,
                    "polish":polish,
                    "slow_plan_fixed":True,
                    "active_plan_policy":"SHIFT_PREVIOUS_COMMITTED_PLAN_ONE_STEP",
                    "online_global_3pct_certificate_claimed":False,
                    "remaining_integer_family_before_optional_polish":"FAST_DISPATCH_MODE_ONLY",
                })
                base.write_json(issue_out/"R26_STEP4_CONDITIONED_SOLVE.json",q)
                solver_rows.append(q)
                print(
                    f"[A 단계4 {issue-112:02d}/54] issue={issue} "
                    f"solver={total:.2f}s residual_int={len(ints)}",
                    flush=True,
                )
                return None

            sm.certified_path_decomposition_solve=conditioned_decomp
            sm.jw=jw_wrapper

            try:
                engine_rc=sm.rolling54_main(engine,work)
            except PlanInvalidation as exc:
                invalidation=exc
                engine_rc=0
                issue_out=engine/f"issue_{exc.issue:06d}"
                detail={
                    "schema_version":"r26.step4_plan_invalidation.v1",
                    "status":"PASS_REPLAN_REQUIRED",
                    "issue":exc.issue,
                    "reasons":list(exc.reasons),
                    "affected_mess_ids":list(exc.affected_mess_ids),
                    "affected_job_ids":list(exc.affected_job_ids),
                    "detail":exc.detail,
                    "current_pre_state_file":str(issue_out/"BUILD7C_PRECOMMIT_STATE.json"),
                    "invalid_issue_committed":False,
                    "future_actual_used":False,
                    "requested_mode":"LOCAL_REPAIR" if (exc.affected_mess_ids or exc.affected_job_ids) else "FULL_REPLAN",
                }
                base.write_json(issue_out/"R26_STEP4_PLAN_INVALIDATION.json",detail)
                base.write_json(run_root/"04_REPLAN_REQUIRED.json",detail)

            base.write_json(run_root/"05_ENGINE_RETURN.json",{
                "return_code":int(engine_rc),
                "plan_invalidation_detected":invalidation is not None,
            })
            if engine_rc!=0:
                raise RuntimeError(f"rolling54_main returned {engine_rc}")

            committed=[]
            for issue in range(113,167):
                d=engine/f"issue_{issue:06d}"
                trp=d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json"
                exp=d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json"
                sp=d/"R26_STEP4_CONDITIONED_SOLVE.json"
                postp=d/"BUILD7C_POSTCOMMIT_STATE.json"
                if not (trp.is_file() and exp.is_file() and sp.is_file() and postp.is_file()):
                    break
                tr=json.loads(trp.read_text());ex=json.loads(exp.read_text());sr=json.loads(sp.read_text())
                committed.append({
                    "issue":issue,
                    "transition_pass":tr.get("status")=="PASS",
                    "fresh_opendss_pass":ex.get("hard_constraint_pass") is True,
                    "post_state_sha256":tr.get("post_state_sha256"),
                    "solver_wall_seconds":sr.get("solver_wall_seconds"),
                    "full_issue_wall_seconds":issue_wall.get(issue),
                })

            prefix_pass=all(r["transition_pass"] and r["fresh_opendss_pass"] for r in committed)
            full54=(len(committed)==54 and invalidation is None)
            replan_pass=(invalidation is not None and prefix_pass)
            if not (full54 or replan_pass):
                raise RuntimeError(
                    f"단계 4 acceptance failed committed={len(committed)} "
                    f"invalidation={invalidation is not None} prefix_pass={prefix_pass}"
                )

            result={
                "schema_version":"conversation_a.step4_local_result.v2",
                "step1":"COMPLETE_54_OF_54",
                "step2":"PASS",
                "step3":"PASS",
                "step4":"PASS_FULL54" if full54 else "PASS_REPLAN_REQUIRED",
                "step5":"PENDING",
                "step6":"PENDING",
                "policy":"SHIFT_PREVIOUS_COMMITTED_ACTIVE_PLAN_ONE_STEP",
                "issues_committed":len(committed),
                "last_committed_issue":committed[-1]["issue"] if committed else None,
                "all_committed_transition_pass":all(r["transition_pass"] for r in committed),
                "all_committed_fresh_opendss_pass":all(r["fresh_opendss_pass"] for r in committed),
                "max_solver_wall_seconds":max((float(r["solver_wall_seconds"] or 0) for r in committed),default=None),
                "max_full_issue_wall_seconds":max((float(r["full_issue_wall_seconds"] or 0) for r in committed),default=None),
                "replan_required":invalidation is not None,
                "replan_issue":invalidation.issue if invalidation is not None else None,
                "replan_reasons":list(invalidation.reasons) if invalidation is not None else [],
                "affected_mess_ids":list(invalidation.affected_mess_ids) if invalidation is not None else [],
                "affected_job_ids":list(invalidation.affected_job_ids) if invalidation is not None else [],
                "requested_mode":(
                    "LOCAL_REPAIR"
                    if invalidation is not None and (invalidation.affected_mess_ids or invalidation.affected_job_ids)
                    else ("FULL_REPLAN" if invalidation is not None else "NONE")
                ),
                "invalid_issue_committed":False if invalidation is not None else None,
                "online_global_3pct_certificate_claimed":False,
                "future_actual_used":False,
                "period_selection_executed":False,
                "repository_modified":False,
                "next_step_if_pass":(
                    "STEP5_LOCAL_REPAIR"
                    if invalidation is not None and (invalidation.affected_mess_ids or invalidation.affected_job_ids)
                    else ("STEP6_FULL_REPLAN" if invalidation is not None else "STEP5_LOCAL_REPAIR_STRESS_GATE")
                ),
                "issues":committed,
            }
            base.write_json(run_root/"A_STEP4_RESULT.json",result)
            print(
                f"PASS_A_STEP4 status={result['step4']} committed={len(committed)} "
                f"replan_issue={result['replan_issue']} mode={result['requested_mode']}",
                flush=True,
            )
            rc=0
        except Exception as exc:
            fail={
                "status":"FAIL_CLOSED",
                "error":f"{type(exc).__name__}: {exc}",
                "traceback":traceback.format_exc(),
                "future_actual_used":False,
                "repository_modified":False,
            }
            base.write_json(run_root/"A_STEP4_FAILURE.json",fail)
            print(json.dumps(fail,indent=2,ensure_ascii=False))
            rc=2
        finally:
            sys.stdout=oldo;sys.stderr=olde
            try: fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
            except Exception: pass

    result_archive,log_archive=base.package_run(
        run_root,base.RESULT_ROOT,base.LOG_ROOT,"ConversationA_STEP4_LOCAL_RESULT"
    )
    print(f"RESULT_HANDOFF_FILE={result_archive}")
    print(f"RESULT_HANDOFF_SHA256={base.sha256(result_archive)}")
    print(f"LOG_HANDOFF_FILE={log_archive}")
    print(f"LOG_HANDOFF_SHA256={base.sha256(log_archive)}")
    print(f"RUN_CONSOLE_LOG={console}")
    return rc


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage2-result",required=True)
    ap.add_argument("--fast-limit-seconds",type=float,default=300.0)
    ap.add_argument("--repo",default=None)
    return run(ap.parse_args())


if __name__=="__main__":
    raise SystemExit(main())
