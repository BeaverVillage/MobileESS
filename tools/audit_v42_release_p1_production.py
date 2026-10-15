"""One admitted Native0 A1 literal replay and current M1 factory build.

No optimize, presolve or IIS. All large source artifacts remain in ignored
runtime storage. This tool does not grant any downstream solve authorization.
"""
import argparse
from contextlib import contextmanager
import gc
import json
from pathlib import Path
import pickle
import sys
import threading
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration.release_p1_acceptance import saved_a1
from v42_integration.m_engine import _write, file_record

OUT = ROOT / 'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/PRODUCTION'
RUNTIME = ROOT / 'runtime/RELEASE_P1_PRODUCTION_NATIVE0_20261015'


@contextmanager
def native0():
    import gurobipy as gp
    originals = {n: getattr(gp.Model, n) for n in ('optimize', 'presolve', 'computeIIS')}
    attempts = []
    def forbidden(*a, **kw):
        attempts.append('FORBIDDEN_NATIVE_ENTRY');raise RuntimeError('RELEASE_PRODUCTION_NATIVE0_ONLY')
    try:
        for name in originals:setattr(gp.Model, name, forbidden)
        yield attempts
    finally:
        for name, method in originals.items():setattr(gp.Model, name, method)


def run():
    import psutil
    import gurobipy as gp
    from v42_integration.d0_case import build_planning_inputs
    from v42_integration.d0_a_planning import build_d0_native_model, _export_d0_point
    from v42_integration.d0_resource import native_binding
    from v42_integration.a_seed import full_replay
    from v42_integration.m_engine import binding, vector_sha, domain_sha
    from v42_integration.a_engine import digest
    from v42_integration.partial_canary import resource_snapshot
    if RUNTIME.exists() and any(RUNTIME.iterdir()):raise FileExistsError('RELEASE_NATIVE0_WINDOW_ALREADY_CONSUMED_NO_REBUILD')
    OUT.mkdir(parents=True, exist_ok=True);RUNTIME.mkdir(parents=True,exist_ok=True)
    began = perf_counter();old = ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json'
    canonical = file_record(old);saved = saved_a1();process = psutil.Process();stop = threading.Event()
    peak = dict(RSS_bytes=0, private_commit_bytes=0, available_RAM_min=psutil.virtual_memory().available)
    def sample():
        while not stop.wait(.2):
            m=process.memory_info();peak['RSS_bytes']=max(peak['RSS_bytes'],m.rss)
            peak['private_commit_bytes']=max(peak['private_commit_bytes'],getattr(m,'private',m.vms))
            peak['available_RAM_min']=min(peak['available_RAM_min'],psutil.virtual_memory().available)
    thread=threading.Thread(target=sample,daemon=True);thread.start();built=None;context=None;mcase=None
    report=dict(status='NOT_CERTIFIED',Native_calls=0,model_builds={},P2_calls=0)
    try:
        with native0() as attempts:
            snapshot=resource_snapshot();_write(OUT/'RESOURCE_BEFORE_NATIVE0.json',snapshot)
            if snapshot['memory']['AvailableMBytes']<8192 or snapshot['memory']['PercentCommittedBytesInUse']>=75:
                raise RuntimeError('RELEASE_NATIVE0_RAM_COMMIT_ADMISSION_FAILED')
            _write(OUT/'NATIVE0_WINDOW_ADMISSION.json',dict(status='PASS',A1_original_rows=844129,A1_columns=36931,
                A1_nnz=10920902,M1_expected_original_columns_approx=344967,
                M1_expected_original_rows_approx=1130336,expected_combined_peak_GiB_upper=8,
                sequential_A1_dispose_before_M1=True,Native_authorization=False))
            _write(RUNTIME/'BUILD_STARTED.json',dict(A1_build_max=1,M1_build_max=1,Native_calls=0))
            context=build_planning_inputs(output=RUNTIME/'CASE',call_cap=120.)
            if (context['manifest']['identity']!=saved['manifest']['identity']
                    or context['input_audit']['a_input_sha']!=saved['input_audit']['a_input_sha']):
                raise ValueError('RELEASE_CURRENT_DESCRIPTOR_SOURCE_CASE_DRIFT')
            case=context['make_a_case']('A1',folder=RUNTIME/'A1_REPLAY')
            t=perf_counter();built=build_d0_native_model(case,build_admission=dict(status='PASS',
                operation='D0_A_NATIVE0_BUILD',case_sha=case.case_sha,concurrent_heavy_solver=False))
            model=built[0];model.Params.Threads=1;model.setObjective(dict(built[2])['rho'],gp.GRB.MINIMIZE);model.update()
            actual=native_binding(model)
            if actual!=saved['certificate']['native_binding']:raise ValueError('RELEASE_A1_LITERAL_MATRIX_DOMAIN_DRIFT')
            full=full_replay(model,saved['point'])
            exported=_export_d0_point(case,built,saved['point'],saved['result']['selected_jobs'])
            if not full['PASS'] or any(digest(value)!=digest(saved['result'][key]) for key,value in exported.items()):
                raise ValueError('RELEASE_A1_RAW_FULL_OR_ORIGINAL_EXPORT_DRIFT')
            objective=dict(coefficients_vector_sha=vector_sha(model.getAttr('Obj')),constant=float(model.ObjCon),
                sense=int(model.ModelSense),nonzero_name='rho_max',nonzero_coefficient=1.)
            objective['objective_sha']=digest(objective)
            if objective!=saved['certificate']['objective']:raise ValueError('RELEASE_A1_ORIGINAL_P1_OBJECTIVE_DRIFT')
            report['model_builds']['A1']=dict(status='PASS_LITERAL_ORIGINAL_FULL_REPLAY',binding=actual,
                Original_FULL=full,objective=objective,stage_case_sha=case.case_sha,
                source_identity=context['manifest']['identity'],source_sha=context['manifest']['source_sha'],
                Original_export_equal=True,wall_seconds=perf_counter()-t)
            _write(OUT/'A1_LITERAL_ORIGINAL_FULL_REPLAY.json',report['model_builds']['A1'])
            model.dispose();built=None;del model;gc.collect()
            snapshot=resource_snapshot();_write(OUT/'RESOURCE_BEFORE_M1_NATIVE0.json',snapshot)
            if snapshot['memory']['AvailableMBytes']<8192 or snapshot['memory']['PercentCommittedBytesInUse']>=75:
                raise RuntimeError('RELEASE_M1_NATIVE0_RAM_COMMIT_ADMISSION_FAILED')
            t=perf_counter();mcase=context['make_m_case']('M1',saved['result'],RUNTIME/'M1')
            b=binding(mcase)
            if mcase.identity['aidc_anchor']!=saved['acceptance']['AIDC_anchor']:
                raise ValueError('RELEASE_CURRENT_M1_A1_FIXED_ANCHOR_DRIFT')
            # Store the exact case once to avoid repeating the expensive Native0
            # factory. This runtime pickle is never a new Source authority.
            packet=RUNTIME/'M1_CURRENT_CASE.pkl'
            with packet.open('wb') as stream:pickle.dump(mcase,stream,pickle.HIGHEST_PROTOCOL)
            report['model_builds']['M1']=dict(status='PASS_CURRENT_ORIGINAL_FACTORY_NATIVE0',binding=b,
                source_identity=context['manifest']['identity'],source_sha=context['manifest']['source_sha'],
                stage_case_sha=mcase.case_sha,AIDC_anchor=saved['result']['aidc_anchor'],
                parent_acceptance_sha=saved['acceptance']['acceptance_sha'],
                original_rows=mcase.original_A.shape[0],original_columns=mcase.original_A.shape[1],
                original_nnz=mcase.original_A.nnz,selected_rows=mcase.A.shape[0],selected_columns=mcase.A.shape[1],
                original_objective_sha=domain_sha({'objective':mcase.original_d['objective'],'constant':mcase.original_d['constant']}),
                transport_original_P1_bit_exact=mcase.identity['transport'].get('original_P1_bit_exact'),
                runtime_packet=file_record(packet),runtime_pickle_is_Source_authority=False,
                solver_calls=0,FULL_integer_point='NOT_RUN',Adaptive_Beam='NOT_RUN',Joint_MILP='NOT_RUN',
                wall_seconds=perf_counter()-t)
            _write(OUT/'M1_CURRENT_FACTORY_NATIVE0.json',report['model_builds']['M1'])
            report.update(status='PASS_A1_LITERAL_REPLAY_AND_CURRENT_M1_FACTORY_ONLY',blocked_Native_attempts=attempts,
                P1_only_handoff=saved['acceptance'],K48='NOT_CERTIFIED_CURRENT_CASE_INCLUSION_PACKET_REQUIRED',
                Actual96='NOT_RUN',Fresh96='NOT_RUN',integrated_production_execution='NOT_CERTIFIED')
    except BaseException as exc:
        report.update(error_type=type(exc).__name__,error=str(exc));raise
    finally:
        if built is not None:built[0].dispose()
        mcase=None;context=None;gc.collect();gp.disposeDefaultEnv();stop.set();thread.join(timeout=2)
        report.update(peak=peak,wall_seconds=perf_counter()-began,canonical_before=canonical,
            canonical_after=file_record(old),immutable_A1_records=saved['immutable_records'],
            audit_tool=file_record(__file__))
        if file_record(old)!=canonical:raise ValueError('RELEASE_CANONICAL_LEDGER_DRIFT')
        if any(file_record(r['path'])!=r for r in saved['immutable_records']):raise ValueError('RELEASE_SAVED_A1_MUTATED')
        _write(OUT/'NATIVE0_PRODUCTION_WINDOW_RESULT.json',report)
    print(json.dumps({k:report[k] for k in ('status','Native_calls','P2_calls','wall_seconds','peak')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native0-window',action='store_true',required=True)
    parser.parse_args();run()
