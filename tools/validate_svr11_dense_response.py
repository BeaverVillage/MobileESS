"""Fresh integrated Source18 structure/proof/readback validation, Native=0.

Input and Forecast authorities alone come from the held campaign. No old
optimization point, bound or start is loaded. optimize/presolve are denied for
the entire construction and native parameter readback. A passing exact proof
and actual dense compression authorize one fresh Root measurement, including
when additional LP-safe physical exclusions are zero.
"""
from collections import Counter
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import sys
import time
import traceback
import numpy as np

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic, read, record, digest, now, sha
from v42_common_campaign.authority import source_files

OLD=Path(r'D:\v42_svr11_may_20261011_16')
DEV=Path(r'D:\v42_dense_response_development_20261011')
DAY='2025-05-01'


def census(A,d):
    row_count=Counter(); row_nnz=Counter(); column_count=Counter(); column_nnz=Counter()
    for name,nnz in zip(d['row_names'],np.diff(A.indptr)):
        family=str(name).split('[',1)[0]
        row_count[family]+=1;row_nnz[family]+=int(nnz)
    degrees=np.bincount(A.indices,minlength=A.shape[1])
    for name,nnz in zip(d['names'],degrees):
        family=str(name).split('[',1)[0]
        column_count[family]+=1;column_nnz[family]+=int(nnz)
    absolute=np.abs(A.data)
    return dict(rows=A.shape[0],columns=A.shape[1],binary=int(np.count_nonzero(d['types']=='B')),
        nnz=int(A.nnz),coefficient_minimum=float(absolute.min()) if len(absolute) else None,
        coefficient_maximum=float(absolute.max()) if len(absolute) else None,
        row_families={f:dict(rows=row_count[f],nnz=row_nnz[f]) for f in sorted(row_count)},
        column_families={f:dict(columns=column_count[f],nnz=column_nnz[f]) for f in sorted(column_count)})


def native_gate(physical, sizes, proof):
    """A completed exact physical proof may legitimately remove zero arcs."""
    added=int(physical.get('additional_exact_removed_arcs',0))
    physical_pass=(physical.get('PASS') is True
        and physical.get('independent_proof',{}).get('PASS') is True
        and physical.get('original_matrix_bridge',{}).get('PASS') is True)
    improved=sizes['Dense']['nnz']<sizes['C3A']['nnz']
    passed=(proof.get('PASS') is True
        and proof.get('integer_and_full_LP_domains_identical') is True and physical_pass and improved)
    return dict(allowed=passed,additional_exact_removed_arcs=added,
        physical_prescreen_completed=physical_pass,zero_additional_exclusions_accepted=True,
        dense_NNZ_improvement=improved,
        reason='READY_FOR_ONE_FRESH_ROOT_MEASUREMENT' if passed else
            'EXACT_OR_STRUCTURE_GATE_NOT_MET',
        maximum_new_Full_calls=1 if passed else 0,maximum_new_Full_seconds=600 if passed else 0,
        Root180_acceptance_seconds=180.,campaign_release_allowed=False)


def run(*,run_root=False):
    if (DEV/'NATIVE0_STARTED.json').exists():
        raise PermissionError('DENSE_NATIVE0_RECEIPT_EXISTS_USE_REVIEWED_NEW_DIRECTORY')
    DEV.mkdir(exist_ok=True)
    output=DEV/'dates/B2'/DAY/'attempts/native0_once/output'
    output.mkdir(parents=True,exist_ok=False)
    sources=source_files();source_sha=digest(sources);started=time.perf_counter()
    runner_sources={name:record(SOURCE/name) for name in (
        'tools/validate_svr11_dense_response.py','tools/root180_completion.py',
        'tools/validate_svr11_root180.py','tools/prepare_svr11_epoch17.py')}
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    atomic(DEV/'NATIVE0_STARTED.json',dict(source_SHA=source_sha,source_commit=source_commit,
        execution_sources=sources,runner_sources=runner_sources,Native_optimize_calls=0,
        Gurobi_presolve_calls=0,UTC=now()))
    def progress(value):
        atomic(DEV/'PROGRESS.json',dict(value,source_SHA=source_sha,
            wall_seconds=time.perf_counter()-started,Native_optimize_calls=0,UTC=now()))
    old=read(OLD/'CAMPAIGN_MANIFEST.json')
    active=copy.deepcopy(old);active['independent_model_proof_replay']=True
    folder=OLD/'inputs/B2'/DAY
    bundle=read(folder/'NATIVE_INPUT.json');fixed=read(folder/'B2_FIXED_AIDC.json')
    if record(fixed['physical']['path'])!=fixed['physical']:
        raise PermissionError('DENSE_FIXED_INPUT_DRIFT')
    with np.load(fixed['physical']['path'],allow_pickle=False) as z:
        planning={k:z[k].copy() for k in z.files}
    payload=dict(bundle=bundle,planning=planning,identity=fixed['identity'],selected_jobs=fixed['selected_jobs'])
    request=dict(root=str(DEV),campaign_root=str(DEV),arm='B2',day=DAY,attempt_id='native0_once',
        output=str(output),source_SHA=source_sha,development_only=True,production_results_promoted=0)
    atomic(DEV/'REQUEST.json',request)
    from v42_svr11.authority import _active
    from v42_thermal.authority import current_authority
    token=_active.set(active);current_authority.cache_clear()
    try:
        import v42_may_campaign_native90.m_model as constructor
        import v42_native.mess as native
        from v42_bootstrap.m1 import native_inputs
        from v42_b2_build_authority_v13.source_port import instrument_builder
        from v42_b2_build_authority_v13.build_runtime import BuildProfile
        from v42_b2_build_authority_v13.scalar_math import original_pcs_math_scope
        from v42_may_campaign_native90.preflight import native_zero
        from v42_ultracompact.native_readback import ROOT_PARAMETERS,snapshot,verify_root_readback
        profile=BuildProfile(source_sha,'OPTIMIZED')
        port,copy_proof=instrument_builder(constructor.__file__,vars(constructor),native_inputs,
            profile,sha(constructor.__file__))
        progress(dict(phase='FRESH_INTEGRATED_NATIVE0_MODEL_BUILD'))
        build_started=time.perf_counter()
        with native_zero() as calls:
            with original_pcs_math_scope(native,native.__file__,sha(native.__file__)):
                case=port(payload,request,progress)
            build_wall=time.perf_counter()-build_started
            proof=constructor.verify_case(case)
            if calls or not proof.get('PASS'):
                raise ValueError('DENSE_NATIVE0_EXACT_PROOF_REQUIRED')
            sizes=dict(Physical=census(case.original_A,case.original_d),
                Compact=census(case.compact.A,case.compact.d),
                Static=census(case.presolve.A,case.presolve.d),
                C3A=census(case.ultra.A,case.ultra.d),Dense=census(case.A,case.d))
            atomic(DEV/'MATRIX_CENSUS.json',sizes)
            progress(dict(phase='NATIVE0_FINAL_MODEL_IDENTITY_AND_PARAMETER_READBACK'))
            from v42_common_mess.model import build,memory_observation
            readback_out=output/'FINAL_NATIVE0_READBACK';readback_out.mkdir()
            model,variables,identity=build(case,readback_out,numeric_parameters=ROOT_PARAMETERS)
            try:
                import gurobipy as gp
                nodes=DEV/'native_nodes';nodes.mkdir(exist_ok=True)
                # Same final overrides as the unrestricted Full entry, applied
                # before actual readback. No Native optimize is invoked here.
                model.Params.MIPGap=.03;model.Params.MIPGapAbs=0.
                model.Params.SolutionLimit=gp.GRB.MAXINT
                model.Params.TimeLimit=600.;model.Params.NodefileDir=str(nodes)
                actual=snapshot(model);checked=verify_root_readback(actual)
                atomic(readback_out/'ACTUAL_PARAMETERS.json',dict(actual,verification=checked))
            finally:model.dispose()
        physical=case.identity['physical_prescreen_authority']['proof']
        if calls:
            raise PermissionError('DENSE_NATIVE0_DENIED_ATTEMPT_PREVENTS_QUALIFICATION')
        gate=native_gate(physical,sizes,proof)
        if source_files()!=sources or any(sha(SOURCE/name)!=item['sha256'] for name,item in runner_sources.items()):
            raise PermissionError('DENSE_VALIDATION_SOURCE_OR_RUNNER_DRIFT')
        report=dict(PASS=True,classification='EXACT_NATIVE0_VALIDATED_ROOT_NOT_MEASURED',
            source_SHA=source_sha,source_commit=source_commit,source_seal=record(DEV/'NATIVE0_STARTED.json'),
            case_SHA=case.case_sha,original_matrix_SHA=case.identity['original_matrix_sha'],
            original_domain_SHA=case.identity['original_domain_sha'],
            selected_matrix_SHA=case.identity['selected_matrix_sha'],
            selected_domain_SHA=case.identity['selected_domain_sha'],
            selected_Bound_SHA=hashlib.sha256(case.d['lower'].tobytes()+case.d['upper'].tobytes()).hexdigest(),
            original_integer_and_fractional_LP_projection_identical=True,
            Native_optimize_calls=0,Gurobi_presolve_calls=0,denied_native_attempts=calls,
            prior_optimization_points_bounds_starts_read=0,sizes=sizes,physical=physical,
            mathematical_proof=proof,Dense_Response_proof=case.identity['response_authority']['proof'],
            model_build_wall_seconds=build_wall,build_profile=profile.receipt(),
            native_parameter_readback=record(readback_out/'ACTUAL_PARAMETERS.json'),
            actual_model_identity=record(readback_out/'MODEL_IDENTITY.json'),
            memory=memory_observation(),copy_elision=copy_proof,Root_measurement_gate=gate,
            final_Gurobi_presolved_NNZ=None,Root_completed_seconds=None,solver_LB=None,solver_gap=None,
            campaign_HOLD=True,production_results_promoted=0,UTC=now())
        atomic(DEV/'NATIVE0_VALIDATION.json',report)
        atomic(DEV/'ROOT_MEASUREMENT_HOLD.json',dict(gate,Native_optimize_calls=0,UTC=now()))
        print(json.dumps(dict(PASS=True,classification=report['classification'],sizes=sizes['Dense'],
            Root_measurement_gate=gate),ensure_ascii=False))
        if run_root:
            if gate.get('allowed') is not True:
                raise PermissionError('DENSE_ROOT_EXACT_OR_COMPRESSION_GATE_NOT_MET')
            from validate_svr11_root180 import measure_case_once
            root=measure_case_once(case,request,sources=sources,source_sha=source_sha,source_commit=source_commit,
                build_wall=build_wall,copy_proof=copy_proof,progress=progress,sizes=sizes)
            report=dict(report,Root_validation=record(__import__('validate_svr11_root180').DEV/'ROOT180_VALIDATION.json'),
                Root_classification=root['classification'])
            atomic(DEV/'INTEGRATED_VALIDATION_INDEX.json',report)
        return report
    except BaseException as error:
        ledger=Path(r'D:\v42_dense_response_root_measurement_20261011')/'NATIVE_RUNTIME_LEDGER.json'
        runtime=read(ledger) if ledger.exists() else None
        atomic(DEV/'VALIDATION_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),
            source_SHA=source_sha,
            Native_optimize_calls=len(runtime['calls']) if runtime is not None and runtime.get('inflight') is None else
                None if runtime is not None else 0,
            Native_Runtime=runtime.get('measured_Native_Runtime') if runtime is not None else 0,
            runtime_ledger=record(ledger) if runtime is not None else None,UTC=now()))
        raise
    finally:_active.reset(token);current_authority.cache_clear()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--root-once',action='store_true')
    run(run_root=parser.parse_args().root_once)
