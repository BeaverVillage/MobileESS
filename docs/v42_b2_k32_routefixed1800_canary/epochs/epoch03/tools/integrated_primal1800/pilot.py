"""Frozen PR216 native worker adaptation; original builders/validators reused."""
from __future__ import annotations
import argparse,gc,math,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.integrated_primal1800.adapter import *
from tools.u4_primal_alns.pilot import PARAMS as PR216_PARAMS, finite_attr
from v42_m1_research.check_ub import vector_sha
require=v.require
GLOBAL_LB=.46498486997548166


def invoke(arguments, log):
    began=time.perf_counter()
    with Path(log).open('w',encoding='utf-8') as stream:
        completed=subprocess.run([sys.executable,'-X','utf8','-m','tools.integrated_primal1800.pilot',*map(str,arguments)],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    return completed.returncode,time.perf_counter()-began


def prepare():
    import shutil
    require(not (DOCS/'RUN_STARTED.json').exists(),'NO_RESTART_OR_BUDGET_RESET')
    initialize_protection()
    write(DOCS/'PRE_RUN_SOURCE_RESOURCE_AUDIT.json',r.audit('CANARY_INITIAL_READONLY',True))
    require(read(DOCS/'PRE_RUN_SOURCE_RESOURCE_AUDIT.json')['PASS'],'SOURCE_RESOURCE_NATIVE0')
    for filename in ('SIGNED_SELECTION_CONTEXT.json','SIGNED_SELECTION_SOURCE_RAW.json',
            'SIGNED_SELECTION_INDEPENDENT_NATIVE0.json','U4_K32_SIGNED_DIAGNOSTICS.json'):
        shutil.copyfile(OLD/filename,DOCS/filename)
    old_compare=read(OLD/'COMPARISON.json')
    # Final and callback points share the same verified objective, but differ
    # slightly in free continuous coordinates. Use the separately saved final
    # point for code-only strict source-box regression; never repair either.
    reference=old_compare['methods']['N1']['iterations'][0]['validated_candidates'][-1]
    ref=reference['raw']['path'];old_replay=reference['replay']['path']
    ref_replay=DOCS/'NATIVE0_REFERENCE_N1_REPLAY.json';shutil.copyfile(old_replay,ref_replay)
    case=v.load_native_case();case.output=DOCS/'native0';case.output.mkdir(exist_ok=True)
    center=v.load_point(ref)
    single,pairs,grid=candidates(case,center)
    proofs=[]
    for method,candidate in [('N1',n.candidate_queue('N1')[0]),('N2+',single[0]),('N3+',pairs[0]),('U4',{})]:
        spec=make_spec(case,center,method,candidate,ref_replay)
        low,high,ham,coeff,rhs,receipt=restriction(case,center,spec)
        proof=audit(case,center,spec,low,high)
        proofs.append(dict(method=method,proof=proof,restriction=receipt))
        if method in ('N2+','N3+'):
            alternative=center.copy();modes=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))
            alternative[modes]=1-alternative[modes]
            require(float(coeff@alternative[ham])==float(coeff@center[ham]),'ALL384_MODE_FLIPS_MUST_NOT_CHANGE_ROUTE_HAMMING')
            bad=dict(spec,hamming_columns=spec['free_binary_columns'])
            rejected=False
            try:audit(case,center,bad,low,high)
            except ValueError:rejected=True
            require(rejected,'REGRESSION_MUST_REJECT_MODE_RADIUS_COUPLING')
            bad_low=low.copy();j=int(np.flatnonzero(np.char.startswith(case.d['names'],'SOC['))[0]);bad_low[j]+=1
            rejected=False
            try:audit(case,center,spec,bad_low,high)
            except ValueError:rejected=True
            require(rejected,'REGRESSION_MUST_REJECT_SOC_RESTRICTION')
    cold=cold_spec(case);low,high,*_=restriction(case,None,cold)
    proofs.append(dict(method='INITIALIZE',proof=audit(case,None,cold,low,high)))
    del case,center,low,high;gc.collect()
    write(DOCS/'PRE_NATIVE0_ADAPTER_REGRESSION.json',dict(PASS=True,proofs=proofs,
        historical_N1_point_used_for_code_validation_only=True,allowed_as_new_solver_start=False,
        Native_optimize_calls=0,all384_Mode_flip_route_Hamming_invariance=True,
        bad_Mode_Hamming_and_SOC_bound_restrictions_rejected=True))
    certificates={}
    for number,value in ((1,.46497617639758426),(2,.46498486997548166)):
        path=ROOT/f'docs/v42_critical_grid_cg/iteration{number:02d}/INDEPENDENT_CERTIFICATE.json'
        packet=read(path)
        require(packet.get('PASS') is True,'HISTORICAL_LB_CERTIFICATE_NOT_PASS')
        require(str(value) in json.dumps(packet),'EXPECTED_LB_NOT_IN_CERTIFICATE')
        require(v.CASE_SHA in json.dumps(packet) and v.SOURCE_SHA in json.dumps(packet),'LB_SOURCE_CASE_MISMATCH')
        certificates['K32' if number==1 else 'K48']=dict(LB=value,certificate=record(path),proof=packet)
    write(DOCS/'LB_PROVENANCE_REUSE.json',dict(PASS=True,certificates=certificates,
        valid_Global_LB=GLOBAL_LB,new_LB_optimize_calls=0,restricted_bounds_used_as_Global_LB=False))
    policy=dict(Native_limit=1800,initial_stage_allocation=dict(A=180,N1=150,N2plus=900,N3plus=570),
        per_call_caps=dict(initialization=120,U4=90,N1=150,N2plus=150,N3plus=180),
        return_reserve_seconds=5,Worker=1,Threads=1,
        next_type_rule='N1 then N2+; no gain => switch N2+/N3+; verified gain => reset current signed-grid queue, prioritize N2+.',
        finite_queue='4 primary +4 expanded single-vehicle domains, 6 pairs per current verified center; mathematical model signatures never repeated.',
        root_stall_rule='After two consecutive TIME_LIMIT root-incomplete calls of a type at one center, defer that type until the other queue is exhausted; then try distinct next domains.',
        Route_Hamming_only=True,all384_Mode_free_in_N2plus_N3plus=True,
        stop_on_first_raw_route_improvement_to_validate_after_worker_exit=True,
        no_previous_incumbent_cold_start=True,new_global_LB_solves=0,unrestricted_full_BB_calls=0)
    write(DOCS/'PREREGISTERED_POLICY.json',policy)
    paths=list((ROOT/'tools/integrated_primal1800').glob('*.py'))
    paths+=list((ROOT/'tools/u4_primal_alns').glob('*.py'))
    paths+=list((ROOT/'v42_common_mess').glob('*.py'))
    paths+=[ROOT/'tools/time_decomposed_lb/grid.py',ROOT/'tools/b2_root_lp_tightening/fractional_grid_oracle.py',
        DOCS/'PREREGISTERED_POLICY.json',DOCS/'PRE_NATIVE0_ADAPTER_REGRESSION.json',DOCS/'LB_PROVENANCE_REUSE.json']
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{str(path.relative_to(ROOT)):v.file_sha(path) for path in paths})
    print(json.dumps(dict(PASS=True,Native_optimize_calls=0,source_sealed=True)))


def run(resume=False):
    require(resume or not (DOCS/'RUN_STARTED.json').exists(),'SINGLE_COLD_CANARY_NO_AUTOMATIC_RESTART')
    guard();began=time.perf_counter()
    write(DOCS/('RUN_RESUMED.json' if resume else 'RUN_STARTED.json'),dict(UTC=r.timestamp()['observed_UTC'],base=BASE,
        Native_limit=1800,existing_N1_solver_start=False,initialization_start=None))
    state=dict(PASS=False,calls=[],iterations=[],Native_used=0.,Best=None,Global_LB=GLOBAL_LB,
        source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,ACTUAL='ACTUAL_NOT_RUN',stopped_reason=None,
        stage_best={},Native_worker=1,Threads=1,new_LB_Optimize_calls=0,unrestricted_Full_BB_calls=0,
        first_new_moving_FULL_plan_Native_seconds=None)
    if resume:
        original=read(DOCS/'EPOCH01_GUARD_STOP/FINAL_STATE.json')
        require(len(original['calls'])==1 and original['calls'][0]['method']=='INITIALIZE'
            and original['Native_used']==80.0460000038147 and original['Best'] is not None,
            'EXACT_ONE_COMPLETED_COLD_CALL_ONLY_RESUME')
        require(read(DOCS/'PRE_NATIVE_U4_GUARD_DENIAL_INDEPENDENT_ACCOUNTING.json')['PASS'],
            'NO_U4_OPTIMIZE_ENTRY_ACCOUNTING_REQUIRED')
        state=original;state.update(PASS=False,stopped_reason=None,error=None,traceback=None,
            epoch01_controller_wall_seconds=original['controller_wall_seconds'],resume_no_initialization_reexecution=True)
        require(read(state['Best']['replay']['path'])['PASS'],'PRESERVED_NEW_COLD_FULL_REPLAY')
    write(DOCS/'LIVE_STATE.json',state)
    def perform(method,candidate=None,pattern=None):
        guard();remaining=1800-state['Native_used']-5
        if remaining<=0:return False
        index=max([0]+[int(p.name.split('_')[0]) for p in (DOCS/'calls').glob('*') if p.is_dir()])+1
        folder=DOCS/'calls'/f'{index:02d}_{method.replace("+","PLUS")}'
        folder.mkdir(parents=True,exist_ok=False)
        case=v.load_native_case();case.point=None
        current=state['Best'];x=None if current is None else v.load_point(current['point']['path'])
        if method=='INITIALIZE':spec=cold_spec(case,pattern)
        elif method=='U4':
            spec_path=folder/'SPEC.json'
            code,wall=invoke(['--mode','selector','--center',current['point']['path'],
                '--replay',current['replay']['path'],'--output',spec_path],folder/'SELECTOR.log')
            require(code==0,'SOURCE_U4_SELECTOR_SUBPROCESS_FAILED')
            spec=read(spec_path)
            require('gurobipy' not in sys.modules,'CONTROLLER_MUST_NOT_LOAD_GUROBI')
        else:spec=make_spec(case,x,method,candidate or {},current['replay']['path'])
        signature=spec.get('mathematical_model_signature')
        if signature in seen:
            write(folder/'SKIP.json',dict(state='SKIPPED_IDENTICAL_MATHEMATICAL_NEIGHBORHOOD',Native_calls=0,signature=signature))
            state['iterations'].append(dict(method=method,candidate=candidate,Native_calls=0,state='DUPLICATE_SKIP'))
            del case;gc.collect();return False
        low,high,*_=restriction(case,x,spec);proof=audit(case,x,spec,low,high,folder/'PRE_NATIVE0.json')
        require(proof['PASS'],'ACTUAL_CENTER_NATIVE0_FAILED')
        write(folder/'SPEC.json',spec)
        if signature:seen.add(signature)
        del case,x,low,high;gc.collect()
        cap={'INITIALIZE':120,'U4':90,'N1':150,'N2+':150,'N3+':180}[method]
        if method in ('INITIALIZE','U4'):
            cap=min(cap,180-sum(c['Native_Runtime'] for c in state['calls'] if c['method'] in ('INITIALIZE','U4'))-5)
        if method=='N2+':cap=min(cap,remaining-570) if state['Native_used']<900 and not any(c['method']=='N3+' for c in state['calls']) else cap
        seconds=min(float(cap),remaining)
        if seconds<=0:return False
        command=['--mode','native','--method',method,'--spec',folder/'SPEC.json','--output',folder/'native','--seconds',seconds]
        if current:command+=['--center',current['point']['path']]
        rc,worker_wall=invoke(command,folder/'WORKER.log')
        path=folder/'native/NATIVE_CALL.json'
        require(path.exists(),'MISSING_NATIVE_RECEIPT_BUDGET_QUARANTINE')
        call=read(path);call['receipt']=record(path);call['worker_exit_code']=rc;call['worker_process_wall_seconds']=worker_wall
        if call['entered_native']:
            runtime=call['Native_Runtime'];require(runtime is not None and math.isfinite(runtime) and runtime>=0,'UNMEASURED_NATIVE_BUDGET_QUARANTINE')
            state['Native_used']+=runtime
            state['calls'].append(call)
        else:
            state['iterations'].append(dict(method=method,PRE_NATIVE_REJECTED=record(path)));write(DOCS/'LIVE_STATE.json',state)
            raise ValueError('PRE_NATIVE_REJECTED_NO_BYPASS')
        require(state['Native_used']<=1800,'ACTUAL_NATIVE_CEILING_BREACH')
        iteration=dict(method=method,candidate=candidate,call=record(path),used_after=state['Native_used'],
            starting_Best_UB=None if current is None else current['UB'],validated=[],ending_Best_UB=None)
        for k,capture in enumerate(call['captures']):
            raw=capture['file']['path'];replay=folder/f'REPLAY_{k:03d}.json'
            vrc,vwall=invoke(['--mode','validate','--point',raw,'--output',replay,'--solver-objective',capture['Solver_ObjVal']],folder/f'VERIFY_{k:03d}.log')
            receipt=read(replay) if replay.exists() else dict(PASS=False,error='VALIDATOR_NO_RECEIPT')
            item=dict(raw=record(raw),replay=record(replay) if replay.exists() else None,PASS=receipt.get('PASS',False),validation_wall_seconds=vwall)
            iteration['validated'].append(item)
            if vrc==0 and receipt.get('PASS'):
                ub=receipt['Global_UB'];require(ub>=GLOBAL_LB-1e-8,'UB_BELOW_CERTIFIED_LB_SOURCE_CONFLICT')
                final_tie=(state['Best'] is not None and ub==state['Best']['UB']
                           and Path(raw).name=='FINAL_RAW.npz')
                if state['Best'] is None or ub<state['Best']['UB'] or final_tie:
                    state['Best']=dict(UB=ub,point=record(raw),replay=record(replay),method=method,
                        acquired_Native_seconds=state['Native_used']-call['Native_Runtime']+capture['discovered_Native_seconds'])
                    if v.vector_sha(v.load_point(raw))==v.INITIAL_VECTOR_SHA:
                        import shutil;shutil.copyfile(replay,DOCS/'INITIAL_U4_INDEPENDENT_REPLAY.json')
        iteration['ending_Best_UB']=None if state['Best'] is None else state['Best']['UB']
        state['iterations'].append(iteration)
        if state['Best']:state['stage_best'][method]=state['Best']['UB']
        write(DOCS/'LIVE_STATE.json',state)
        stop=call.get('callback_stop_reason')
        require(call.get('Status')!=12 and stop not in ('RESOURCE_OR_SOURCE_CALLBACK_GATE','CALLBACK_ERROR'),'RESOURCE_NUMERIC_OR_SOURCE_STOP')
        require(rc==0,'NATIVE_CALL_FAILURE')
        return current is None and state['Best'] is not None or current is not None and state['Best'] is not None and state['Best']['UB']<current['UB']
    seen=set()
    try:
        if not resume:
            for pattern in ('all_discharge','before_peak'):
                if perform('INITIALIZE',pattern=pattern):break
        if state['Best'] is None:state['stopped_reason']='NO_NEW_FULL_FEASIBLE';return
        state['cold_initial_FULL_UB']=state['Best']['UB']
        perform('U4');state['fresh_U4_FULL_UB']=state['Best']['UB']
        perform('N1',n.candidate_queue('N1')[0]);state['fresh_N1_FULL_UB']=state['Best']['UB']
        next_method='N2+';queues={};queue_center=None;stalls={'N2+':0,'N3+':0}
        while 1800-state['Native_used']>5:
            best=state['Best'];gap=(best['UB']-GLOBAL_LB)/best['UB']
            if gap<=.03:state['stopped_reason']='GLOBAL_GAP_3PCT_CERTIFIED';break
            sha=best['point']['sha256']
            if sha!=queue_center:
                case=v.load_native_case();x=v.load_point(best['point']['path'])
                single,pairs,grid=candidates(case,x);del case,x;gc.collect()
                queues={'N2+':single,'N3+':pairs};queue_center=sha;stalls={'N2+':0,'N3+':0}
                state.setdefault('center_reselections',[]).append(dict(center=best['point'],replay=best['replay'],grid=grid,units=[c['selected_units'] for c in single[:4]]))
            other='N3+' if next_method=='N2+' else 'N2+'
            if not queues[next_method] or stalls[next_method]>=2 and queues[other]:next_method=other;other='N3+' if next_method=='N2+' else 'N2+'
            if not queues[next_method]:state['stopped_reason']='FINITE_NONREPEATING_VALID_NEIGHBORHOOD_EXHAUSTED';break
            candidate=queues[next_method].pop(0);before_calls=len(state['calls']);gain=perform(next_method,candidate)
            if len(state['calls'])>before_calls:
                last=state['calls'][-1]
                stalls[next_method]=stalls[next_method]+1 if last['Status']==9 and last['root_completed_Native_seconds'] is None else 0
            next_method='N2+' if gain else other
        if state['stopped_reason'] is None:state['stopped_reason']='NATIVE_BUDGET_EXHAUSTED_WITH_RETURN_RESERVE'
        state['PASS']=state['Best'] is not None
    except Exception as exc:
        state.update(stopped_reason='RESOURCE_NUMERIC_SOURCE_OR_IMPLEMENTATION_STOP',error=repr(exc),traceback=traceback.format_exc(),PASS=state['Best'] is not None)
    finally:
        state['controller_wall_seconds']=time.perf_counter()-began
        state['final_Global_gap_percent']=None if state['Best'] is None else 100*(state['Best']['UB']-GLOBAL_LB)/state['Best']['UB']
        state['Global_gap_3pct_certified']=state['final_Global_gap_percent'] is not None and state['final_Global_gap_percent']<=3
        write(DOCS/'FINAL_STATE.json',state);write(DOCS/'LIVE_STATE.json',state)
        write(DOCS/'POST_RUN_SOURCE_RESOURCE_AUDIT.json',r.audit('CANARY_POST_RUN_READONLY',True))
        print(json.dumps(dict(Best=state['Best'],Native_used=state['Native_used'],stopped_reason=state['stopped_reason'])))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['prepare','run','resume','selector','native','validate'],required=True)
    parser.add_argument('--method');parser.add_argument('--spec',type=Path);parser.add_argument('--center',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--seconds',type=float);parser.add_argument('--point',type=Path)
    parser.add_argument('--solver-objective',type=float)
    parser.add_argument('--replay',type=Path)
    args=parser.parse_args()
    if args.mode=='prepare':prepare()
    elif args.mode=='run':run()
    elif args.mode=='resume':run(resume=True)
    elif args.mode=='selector':
        case=v.load_native_case();x=v.load_point(args.center)
        spec=make_spec(case,x,'U4',{},args.replay)
        low,high,*_=restriction(case,x,spec);proof=audit(case,x,spec,low,high)
        require(proof['PASS'],'SOURCE_SELECTOR_NATIVE0')
        write(args.output,spec)
        print(json.dumps(dict(PASS=True,Native_calls=0,Source_U4_selector_unchanged=True,
            Gurobi_DLL_may_be_loaded_but_no_model_constructed_or_optimized=True)))
    elif args.mode=='native':sys.exit(native(args))
    else:
        try:
            result=v.validate(args.point,solver_objective=args.solver_objective,output=args.output)
        except Exception as exc:
            write(args.output,dict(PASS=False,error=repr(exc),traceback=traceback.format_exc(),Raw_not_repaired=True));raise
        print(json.dumps(dict(PASS=result['PASS'],UB=result.get('Global_UB'))));sys.exit(0 if result['PASS'] else 2)


def native(args):
    """Worker exits before any FULL CSR validation is loaded."""
    load_native_case, audit_neighborhood = v.load_native_case, audit
    from v42_common_mess.model import build
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    spec = read(args.spec)
    center = None if args.center is None else v.load_point(args.center)
    PARAMS = dict(PR216_PARAMS, Method=1 if args.method == "INITIALIZE" else 2)
    require(0 < args.seconds <= 600, 'FINITE_CUMULATIVE_TIMELIMIT_REQUIRED')
    require(read(OLD / 'HISTORICAL_PRIMAL_ALNS_AUDIT.json')['PASS'], 'PRIMARY_HISTORY_REQUIRED')
    guard()
    pre = r.audit('PRE_NATIVE_BUILD')
    write(out / 'PRE_BUILD_GATE.json', pre)
    require(pre['PASS'], 'PRE_BUILD_RESOURCE_OR_SOURCE_GATE')
    case = load_native_case()
    case.point = None # Authority reference points are never cold solver starts.
    if center is not None:
        require(args.center.resolve().is_relative_to((DOCS/"calls").resolve()), "ONLY_THIS_CANARY_NATIVE_OUTPUT_START")
    pre_build = r.memory()
    lower, upper, free, coefficients, rhs, restrictions = restriction(case, center, spec)
    proof = audit_neighborhood(case, center, spec, lower, upper, output=out/'INDEPENDENT_RESTRICTION_NATIVE0.json')
    require(proof['PASS'], 'INDEPENDENT_NEIGHBORHOOD_NATIVE0')
    write(out / 'RESTRICTION_NATIVE0.json', restrictions)
    write(out / 'NEIGHBORHOOD.json', spec)
    model = None
    entered = False
    ledger = dict(schema='V42_PRIMAL_RESTRICTED_NATIVE_CALL_V1', method=args.method,
                  entered_native=False, requested_seconds=args.seconds, effective_TimeLimit=args.seconds,
                  Native_Runtime=None, runtime_unavailable=True, Native_worker=1, Threads=1,
                  initial_point=None if center is None else record(args.center), center_vector_sha256=None if center is None else vector_sha(center),
                  previous_PR216_result_solver_start=False,
                  restricted_ObjBound_is_Global_LB=False, existing_Global_LB=GLOBAL_LB,
                  unrestricted_Full_global_BB_calls=0, captures=[], resource_samples=[],
                  callback_errors=[], source_parameters=PARAMS, ACTUAL='ACTUAL_NOT_RUN')
    ledger['execution_source_seal'] = record(DOCS/'EXECUTED_SOURCE_HASHES.json')
    ledger['specification_input'] = record(args.spec)
    write(out / 'NATIVE_CALL.json', ledger)
    try:
        # Common build spec=None permits exact continuous route fixation. Its
        # spec=None continuous-bound check is vacuous; the adapter's separate
        # restriction receipt above proves every continuous change explicitly.
        model, variables, common_identity = build(case, out, lower=lower, upper=upper,
                                                  start=center, spec=None,
                                                  numeric_parameters=PARAMS)
        require(not common_identity['unrestricted_original_C3A_MILP'], 'FORBIDDEN_UNRESTRICTED_MODEL')
        hamming = None if args.method == 'INITIALIZE' else model.addConstr(coefficients @ variables[free] <= rhs,
                                 name='INTEGRATED_ROUTE_ONLY_HAMMING_NEVER_GLOBAL_CUT')
        model.Params.TimeLimit = args.seconds
        model.update()
        import gurobipy as gp
        if hamming is not None:
            row = model.getRow(hamming)
            actual = {int(row.getVar(i).index): float(row.getCoeff(i)) for i in range(row.size())}
            expected = {int(j): float(c) for j,c in zip(free,coefficients)}
            require(actual == expected and hamming.RHS == rhs and hamming.Sense == '<', 'HAMMING_NATIVE_READBACK')
        if center is None:
            require(model.NumStart == 0, 'COLD_MUST_HAVE_NO_MIP_START')
        ledger['actual_NumStart'] = model.NumStart
        params = {key: getattr(model.Params, key) for key in PARAMS}
        params['TimeLimit'] = model.Params.TimeLimit
        require(all(params[key] == value for key, value in PARAMS.items()), 'PARAMETER_READBACK_DRIFT')
        identity = dict(PASS=True, common_model_identity=record(out/'MODEL_IDENTITY.json'),
                        common_builder_reused_unchanged=True, original_Dense_rows_exact=True,
                        added_rows=int(hamming is not None), model_rows=model.NumConstrs, model_columns=model.NumVars,
                        total_binary=int(np.count_nonzero(case.d['types'] != 'C')),
                        restrictions=restrictions, actual_parameter_readback=params,
                        native_hamming_exact=True, unrestricted_global_BB=False,
                        common_spec_None_continuous_check_vacuous=True,
                        continuous_bound_changes_certified_by_adapter=True)
        write(out / 'ADAPTER_MODEL_IDENTITY.json', identity)
        post_build = r.memory()
        gate = r.admit(pre_build, post_build)
        write(out / 'POST_BUILD_NATIVE_ADMISSION.json', gate)
        require(gate['PASS'], 'POST_BUILD_NATIVE_ADMISSION_REJECTED')
        # Close the entry/build race: verify the sealed code and policy again
        # immediately before the immutable model's single Optimize call.
        guard()
        ledger['model_build_wall_seconds'] = time.perf_counter() - began
        ledger['parameter_readback'] = params
        ledger['build_memory_before'] = pre_build
        ledger['build_memory_after'] = post_build
        next_gate = 0.
        best_seen = math.inf if center is None else float(case.d['objective'] @ center + float(case.d['constant']))
        root_complete = None
        stop_reason = None
        def capture(m, where):
            nonlocal next_gate, best_seen, root_complete, stop_reason
            try:
                if where == gp.GRB.Callback.POLLING:
                    return
                runtime = float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if runtime >= next_gate:
                    next_gate = runtime + 10.
                    sample = r.memory()
                    guard()
                    safety = r.callbackcheck()
                    ledger['resource_samples'].append(dict(Native_elapsed=runtime, sample=sample, safety=safety))
                    if not safety['PASS']:
                        stop_reason = 'RESOURCE_OR_SOURCE_CALLBACK_GATE'
                        m.terminate()
                        return
                    write(out / 'LIVE_NATIVE.json', dict(method=args.method, Native_elapsed=runtime,
                          observed_incumbent=None if not math.isfinite(best_seen) else best_seen, validated_new_UB=False, memory=sample))
                if where == gp.GRB.Callback.MESSAGE:
                    text = m.cbGet(gp.GRB.Callback.MSG_STRING)
                    if text.lstrip().startswith('Root relaxation: objective') and not any(
                            token in text.lower() for token in ('interrupted','time limit','infeasible','unbounded')):
                        root_complete = runtime
                if where == gp.GRB.Callback.MIPSOL:
                    objective = float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                    if objective < best_seen:
                        raw = np.asarray(m.cbGetSolution(variables), dtype=np.float64)
                        path = out / f'RAW_{len(ledger["captures"]):03d}.npz'
                        np.savez_compressed(path, point=raw)
                        ledger['captures'].append(dict(file=record(path), Solver_ObjVal=objective,
                              discovered_Native_seconds=runtime, vector_sha256=vector_sha(raw), validated=False))
                        best_seen = objective
                        write(out / 'NATIVE_CALL.json', ledger)
                        if args.method in ('N2+', 'N3+'):
                            stop_reason = 'FIRST_RAW_IMPROVEMENT_EXIT_FOR_IMMEDIATE_FULL_REPLAY'
                            m.terminate()
            except Exception as exc:
                ledger['callback_errors'].append(repr(exc))
                stop_reason = 'CALLBACK_ERROR'
                m.terminate()
        entered = True
        ledger['entered_native'] = True
        ledger['status'] = 'INFLIGHT'
        write(out / 'NATIVE_CALL.json', ledger)
        optimize_start = time.perf_counter()
        try:
            model.optimize(capture)
            ledger['status'] = 'FINISHED'
        except Exception as exc:
            ledger.update(status='FAILED', error=repr(exc), traceback=traceback.format_exc())
        finally:
            ledger['Optimize_return_wall_seconds'] = time.perf_counter() - optimize_start
            runtime = finite_attr(model, 'Runtime')
            ledger['Native_Runtime'] = runtime
            ledger['runtime_unavailable'] = runtime is None
            ledger['Solver_return_overhead_seconds'] = None if runtime is None else max(0., ledger['Optimize_return_wall_seconds'] - runtime)
            ledger['actual_TimeLimit_overrun_seconds'] = None if runtime is None else max(0., runtime - args.seconds)
            for key in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount','MemUsed','MaxMemUsed'):
                ledger[key] = finite_attr(model, key)
            ledger['root_completed_Native_seconds'] = root_complete
            ledger['callback_stop_reason'] = stop_reason
            if finite_attr(model, 'SolCount'):
                raw = np.asarray(variables.X, dtype=np.float64)
                path = out / 'FINAL_RAW.npz'
                np.savez_compressed(path, point=raw)
                ledger['captures'].append(dict(file=record(path), Solver_ObjVal=finite_attr(model,'ObjVal'),
                      discovered_Native_seconds=finite_attr(model,'Runtime'), vector_sha256=vector_sha(raw), validated=False))
            ledger['after_native_memory'] = r.memory()
    except Exception as exc:
        ledger.update(status='FAILED' if entered else 'PRE_NATIVE_REJECTED', error=repr(exc), traceback=traceback.format_exc())
        if entered and model is not None:
            ledger['Native_Runtime'] = finite_attr(model, 'Runtime')
            ledger['runtime_unavailable'] = ledger['Native_Runtime'] is None
    finally:
        write(out / 'NATIVE_CALL.json', ledger)
        if model is not None:
            model.dispose()
        del case
        gc.collect()
        ledger['worker_wall_seconds'] = time.perf_counter() - began
        ledger['Native_Model_disposed_before_FULL_replay'] = True
        write(out / 'NATIVE_CALL.json', ledger)
    print(json.dumps(dict(output=str(out), status=ledger.get('status'), Native_Runtime=ledger.get('Native_Runtime'),
                         ObjVal=ledger.get('ObjVal'), restricted_ObjBound=ledger.get('ObjBound')), ensure_ascii=False))
    return 0 if ledger.get('status') == 'FINISHED' else 2


if __name__=='__main__':main()

