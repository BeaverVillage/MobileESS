"""Bounded LP diagnostic of the saved ORIGINAL S1 FULL96 native matrix."""
from pathlib import Path
from time import perf_counter
import argparse
from fractions import Fraction
import json
import sys
import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write, file_record, matrix_sha, domain_sha, vector_sha
from v42_integration.unified_resource import UnifiedResearchBudget


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode-hull-cuts',type=Path)
    parser.add_argument('--attempt',type=int,default=1)
    args=parser.parse_args()
    strengthened=args.mode_hull_cuts is not None
    output=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP'
    runtime=ROOT/('runtime/FOLLOWUP_S1_MODE_HULL_LP_30S' if strengthened else 'runtime/FOLLOWUP_S1_LP_30S')
    if args.attempt!=1:runtime=runtime.with_name(runtime.name+'_ATTEMPT'+str(args.attempt))
    runtime.mkdir(parents=True,exist_ok=False)
    cert_path=ROOT/'docs/v42_unified_aidc_mess_research_20261014/MEASURED_MESS_FULL96/FULL96_COMPRESSION_CERTIFICATE.json'
    cert=json.loads(cert_path.read_text(encoding='utf8'))
    if not cert['PASS'] or not cert['FULL96_original_rows_captured'] or cert['slots_captured']!=96:
        raise ValueError('S1_ORIGINAL_FULL96_SOURCE_REQUIRED')
    def checked(record):
        actual=file_record(record['path'])
        if any(actual[k]!=record[k] for k in ('path','sha256','bytes')):
            raise ValueError('S1_CACHED_SOURCE_BYTE_DRIFT')
        return Path(record['path'])
    budget=UnifiedResearchBudget()
    if budget.remaining(reserve=30.)<30.:raise RuntimeError('S1_LP_RETURN_BUDGET_GATE')
    _write(runtime/'RESOURCE_ADMISSION.json',budget.preflight())
    began=perf_counter()
    a=sparse.load_npz(checked(cert['original_full_native_CSR'])).tocsr()
    with np.load(checked(cert['original_full_native_domain']),allow_pickle=False) as z:
        d={k:z[k].copy() for k in z.files}
    if matrix_sha(a)!=cert['captured_original_matrix_sha'] or domain_sha(d)!=cert['original_domain_sha']:
        raise ValueError('S1_ORIGINAL_MATRIX_DOMAIN_DRIFT')
    source_a_sha=matrix_sha(a);source_d_sha=domain_sha(d);cut_authority=None;added=0
    if strengthened:
        folder=args.mode_hull_cuts.resolve()
        authority=folder/'ALL_CUTS_AUTHORITY.json'
        cut_authority=json.loads(authority.read_text(encoding='utf8'))
        proof=cut_authority.get('integer_validity',{})
        if (cut_authority.get('status')!='PASS' or cut_authority.get('source_identity')!=cert['identity'] or
                proof.get('PASS') is not True or proof.get('original_single_integer_path_theorem_verified') is not True or
                proof.get('original_mode_and_connection_rows_exact') is not True or
                proof.get('all_original_integer_routes_preserved') is not True or
                proof.get('route_pool_restriction_added') is not False or proof.get('source_domain_sha')!=source_d_sha):
            raise ValueError('S1_SOURCE_SCOPED_ALL_INTEGER_MODE_HULL_PROOF_REQUIRED')
        checked(proof['physical_CSR']);checked(proof['route_source'])
        cuts=sparse.load_npz(folder/'ALL_CUTS_A.npz').tocsr()
        with np.load(folder/'ALL_CUTS_DATA.npz',allow_pickle=False) as z:
            extra={k:z[k].copy() for k in z.files}
        from v42_integration.mess_mode_hull import aggregate_mode_hull_diagnostic
        candidate=aggregate_mode_hull_diagnostic(d,proof['power_limit_kW'])['candidate_rows']
        ri=[];ci=[];values=[]
        for i,row in enumerate(candidate):
            for j,value in row['terms'].items():
                ri.append(i);ci.append(int(j));values.append(float(Fraction(value)))
        expected=sparse.csr_matrix((np.asarray(values),(ri,ci)),shape=(len(candidate),a.shape[1]))
        if (matrix_sha(cuts)!=cut_authority['cut_matrix_sha'] or matrix_sha(cuts)!=matrix_sha(expected) or
                len(extra['rhs'])!=cuts.shape[0] or not np.all(extra['sense']=='<') or
                not np.array_equal(extra['rhs'],np.asarray([float(Fraction(row['rhs'])) for row in candidate])) or
                not np.array_equal(extra['row_names'],np.asarray([row['name'] for row in candidate]))):
            raise ValueError('S1_PROVEN_MODE_HULL_CUT_PACKET_DRIFT')
        # Do not alter any original row, physical bound or objective.
        a=sparse.vstack((a,cuts),format='csr');added=cuts.shape[0]
        for key in ('rhs','sense','row_names'):d[key]=np.r_[d[key],extra[key]]
    rho=np.flatnonzero(d['names']=='rho_max')
    if (len(rho)!=1 or np.count_nonzero(d['objective'])!=1 or d['objective'][rho[0]]!=1. or float(d['constant'])!=0.):
        raise ValueError('S1_ORIGINAL_MIN_RHO_OBJECTIVE_REQUIRED')
    import gurobipy as gp
    model=gp.Model('S1_ORIGINAL_FULL96_CONTINUOUS_RELAXATION_DIAGNOSTIC')
    try:
        model.Params.Threads=1;model.Params.Method=2;model.Params.Crossover=0
        model.Params.FeasibilityTol=1e-9;model.Params.OptimalityTol=1e-9;model.Params.NumericFocus=3
        model.Params.LogFile=str(runtime/'NATIVE.log')
        x=model.addMVar(a.shape[1],lb=d['lower'],ub=d['upper'],vtype='C',obj=d['objective'])
        x.VarName=d['names'].tolist();model.ObjCon=float(d['constant']);model.ModelSense=gp.GRB.MINIMIZE
        rows=model.addMConstr(a,x,d['sense'],d['rhs']);rows.ConstrName=d['row_names'].tolist();model.update()
        if (matrix_sha(model.getA().tocsr())!=matrix_sha(a) or
                not np.array_equal(np.asarray(model.getAttr('RHS')),d['rhs']) or
                not np.array_equal(np.asarray(model.getAttr('Sense')),d['sense']) or
                not np.array_equal(x.LB,d['lower']) or not np.array_equal(x.UB,d['upper']) or
                not np.array_equal(x.Obj,d['objective']) or not np.all(x.VType=='C')):
            raise ValueError('S1_NATIVE_RELAXATION_READBACK_DRIFT')
        build_wall=perf_counter()-began
        budget.stage_context=dict(scale_stage='S1',planning_stage='M1',
            reduced_case_sha=cert['identity']['reduced_case_sha'],captured_bindings=cert['identity'],
            original_source_matrix_sha=source_a_sha,original_source_domain_sha=source_d_sha,
            strengthened_matrix_sha=matrix_sha(a),mode_hull_cut_authority=cut_authority,
            source_certificate=file_record(cert_path),relaxation='ALL_ORIGINAL_INTEGER_TYPES_TO_C',
            objective='EXPLICIT_MINIMIZE_ORIGINAL_RHO',Original_4x24_bound_transfer=False)
        call=budget.solve(model,label='MESS:S1:MODE_HULL_LP_DIAGNOSTIC' if strengthened else 'MESS:S1:ORIGINAL_ROOT_LP_DIAGNOSTIC',cap=30.)
        result=dict(status='NOT_CERTIFIED',scope='S1_ORIGINAL_FULL96_LP_DIAGNOSTIC_ONLY',
            original_source_identity=cert['identity'],original_matrix_sha=source_a_sha,original_domain_sha=source_d_sha,
            evaluated_matrix_sha=matrix_sha(a),evaluated_domain_sha=domain_sha(d),mode_hull_authority=cut_authority,
            build_wall_seconds=build_wall,Native_call=call,Native_Runtime=float(model.Runtime),
            solver_status=int(model.Status),SolCount=int(model.SolCount),
            certified_original_4x24_Global_LB=None,Original_4x24_bound_transfer=False,
            integer_optimal_value_status='NOT_CERTIFIED',new_valid_cuts_applied=added)
        if model.SolCount:
            point=np.asarray(x.X,dtype=np.float64);activity=np.asarray(a@point).ravel()-d['rhs']
            residual=np.where(d['sense']=='<',np.maximum(activity,0),
                np.where(d['sense']=='>',np.maximum(-activity,0),np.abs(activity)))
            bounds=max(0.,float(np.max(d['lower']-point)),float(np.max(point-d['upper'])))
            np.savez_compressed(runtime/'LP_POINT.npz',point=point,names=d['names'])
            groups={}
            for family in ('arc','charge_mode','node_active','connected','SOC','Pch','Pdis','Q'):
                indices=np.asarray([i for i,n in enumerate(d['names']) if str(n).startswith(family+'[')],int)
                integer=indices[d['types'][indices]!='C']
                frac=integer[np.abs(point[integer]-np.rint(point[integer]))>1e-7]
                groups[family]=dict(columns=len(indices),original_integer_columns=len(integer),
                    fractional_integer_columns=len(frac),examples=[dict(name=str(d['names'][i]),value=float(point[i])) for i in frac[:20]])
            result.update(status='DIAGNOSTIC_ONLY',lp_objective=float(model.ObjVal),
                original_row_max_residual=float(np.max(residual)),bound_max_residual=bounds,
                original_LP_feasible_point_PASS=max(float(np.max(residual)),bounds)<=1e-8,
                fractional_groups=groups,LP_point=file_record(runtime/'LP_POINT.npz'),point_sha=vector_sha(point),
                same_source_comparison_integer_UB=0.6412659669740282,
                same_source_UB_scope='HISTORICAL_S1_INTEGER_FEASIBLE_NOT_INTEGER_OPTIMUM',
                integer_UB_minus_LP=float(0.6412659669740282-model.ObjVal),
                row_fractionality_point_claimed=True)
        else:result['fractionality_status']='NO_LP_POINT_BEFORE_30_SECOND_LIMIT'
        if strengthened:
            base=json.loads((output/'S1_ROOT_FRACTIONALITY.json').read_text(encoding='utf8'))
            result.update(baseline_S1_LP_objective=base['lp_objective'],
                LP_objective_increase=None if not model.SolCount else float(model.ObjVal-base['lp_objective']),
                numerical_diagnostic_not_exact_dual_certificate=True)
        _write(output/('S1_MODE_HULL_LP_COMPARISON.json' if strengthened else 'S1_ROOT_FRACTIONALITY.json'),result)
        _write(runtime/'RESULT.json',result)
        print(json.dumps({k:result.get(k) for k in ('status','solver_status','SolCount','lp_objective','original_LP_feasible_point_PASS','fractionality_status')},indent=2))
    finally:model.dispose()


if __name__=='__main__':main()
