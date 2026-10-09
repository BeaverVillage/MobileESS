"""Post-Native independent scientific admission; never constructs a solver.

Only new hybrid verification artifacts are written.  Native-run outputs and all
completed historical proofs are read-only.  A producer PASS, RMP objective, or
local MIP BestBd cannot replace an original-matrix weak-duality certificate.
"""
from fractions import Fraction as F
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import pickle
from time import perf_counter

import numpy as np

from v42_m1_research.escape_audit import _load_case_read_only
from v42_m1_research.check_ub import validate_candidate, vector_sha
from v42_unified.mess_replay import graph_from_bundle
from . import verify
from .blocks import build_blocks

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'docs/v42_m1_fast_hybrid_20261008'
RUNTIME=ROOT/'runtime/v42_m1_fast_hybrid'
EXPECTED_PARAMETERS=dict(Threads=1,MIPGap=.005,FeasibilityTol=1e-8,
                         OptimalityTol=1e-8,IntFeasTol=1e-8)
ALLOCATIONS=dict(UB=1350.,PRICING=1200.,RMP=150.)


def _under(path,parent,label):
    p=Path(path).resolve()
    if ROOT.resolve().drive.upper()!='D:' or p.drive.upper()!='D:' or not p.is_relative_to(Path(parent).resolve()):
        raise ValueError('HYBRID_FINAL_D_PATH_REQUIRED:'+label)
    return p


def _output(path):
    p=_under(path,ROOT,'OUTPUT')
    if p.is_relative_to(ROOT/'docs') and not p.is_relative_to(REPORTS):
        raise ValueError('HYBRID_FINAL_HISTORICAL_REPORT_WRITE_FORBIDDEN')
    p.mkdir(parents=True,exist_ok=True)
    return p


def _write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def _raw(path,evidence,expected=None):
    path=_under(path,ROOT,'EVIDENCE');raw=path.read_bytes();digest=sha256(raw).hexdigest()
    if expected is not None and digest!=expected:raise ValueError('HYBRID_FINAL_PACKET_SHA_DRIFT:'+path.name)
    evidence[str(path)]=digest
    return raw


def _json(path,evidence,expected=None):
    return json.loads(_raw(path,evidence,expected))


def _packet(record,path,evidence):
    path=_under(path,ROOT,'RECORDED_PACKET')
    if not isinstance(record,dict) or _under(record.get('path',''),ROOT,'RECORDED_PATH')!=path:
        raise ValueError('HYBRID_FINAL_PACKET_PATH_BINDING_DRIFT:'+path.name)
    if not isinstance(record.get('sha256'),str) or len(record['sha256'])!=64:
        raise ValueError('HYBRID_FINAL_PACKET_SHA_MISSING:'+path.name)
    return _json(path,evidence,record['sha256'])


def _case_bind(value,expected):
    if isinstance(value,dict):
        if 'case_sha' in value and value['case_sha']!=expected:
            raise ValueError('HYBRID_FINAL_EVIDENCE_CASE_MISMATCH')
        for child in value.values():_case_bind(child,expected)
    elif isinstance(value,(list,tuple)):
        for child in value:_case_bind(child,expected)


def _dual(value,size):
    if not isinstance(value,dict):raise ValueError('HYBRID_FINAL_RATIONAL_DUAL_DICT_REQUIRED')
    result={}
    for key,q in value.items():
        i=int(key)
        if str(i)!=str(key) or not 0<=i<size:raise ValueError('HYBRID_FINAL_RATIONAL_DUAL_AXIS_DRIFT')
        q=F(q)
        if q:result[str(i)]=str(q)
    return result


def _display_bound(exact,*,lower):
    """Keep the displayed binary64 bound on the proved side of the rational."""
    q=F(exact);value=float(q)
    if (lower and F(value)>q) or (not lower and F(value)<q):
        value=float(np.nextafter(value,-np.inf if lower else np.inf))
    return value


def _project(value,rows):
    return {str(j):value[str(int(i))] for j,i in enumerate(rows) if str(int(i)) in value}


def load_case_read_only():
    """Restore graph only from SHA-verified completed D copies, with no writes."""
    case=_load_case_read_only()
    identity=json.loads(verify._committed(verify.PREVIOUS+'SCIENTIFIC_MODEL_IDENTITY.json'))
    if case.case_sha!=identity['case_sha']:raise ValueError('HYBRID_FINAL_COMPLETED_CASE_MISMATCH')
    copies={}
    for row in identity['D_frozen_copies']:
        p=_under(row['local_path'],ROOT,'COMPLETED_FROZEN_COPY')
        if sha256(p.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('HYBRID_FINAL_FROZEN_COPY_SHA_DRIFT')
        copies[Path(row['original_path']).name]=p
    if sha256(copies['DATA.pkl'].read_bytes()).hexdigest()!=identity['frozen_bundle_sha256']:
        raise ValueError('HYBRID_FINAL_AIDC_IDENTITY_DRIFT')
    if sha256(copies['ROUTE_TABLE.json.gz'].read_bytes()).hexdigest()!=identity['route_table_sha256']:
        raise ValueError('HYBRID_FINAL_ROUTE_IDENTITY_DRIFT')
    with copies['DATA.pkl'].open('rb') as stream:data=pickle.load(stream)
    bundle=dict(data[0]);route=dict(bundle['route_table'])
    if bundle['day']!='2025-05-01' or len(data[1])!=1499 or route['sha256']!=identity['route_table_sha256']:
        raise ValueError('HYBRID_FINAL_FROZEN_DAY_JOBS_ROUTE_DRIFT')
    route['path']=str(copies['ROUTE_TABLE.json.gz']);bundle['route_table']=route
    case.graph=graph_from_bundle(bundle)
    with np.load(io.BytesIO(verify._committed(verify.PREVIOUS+'FINAL_STRICT_ADMITTED_UB_POINT.npz')),allow_pickle=False) as z:
        case.point=z['point'].copy()
    return case


def _strict_ub(case,path,evidence):
    raw=_raw(path,evidence)
    with np.load(io.BytesIO(raw),allow_pickle=False) as z:
        if z.files!=['point']:raise ValueError('HYBRID_FINAL_UB_PACKET_AXIS_DRIFT')
        point=z['point'].copy()
    if point.dtype!=np.dtype('float64') or point.shape!=(case.A.shape[1],) or not np.isfinite(point).all():
        raise ValueError('HYBRID_FINAL_UB_RAW_POINT_DRIFT')
    original=case.lift(point)
    for d,x,label in ((case.d,point,'C3A'),(case.original_d,original,'FULL')):
        discrete=x[d['types']!='C'];binary=x[d['types']=='B']
        if not np.all(discrete==np.rint(discrete)) or not np.all((binary==0.)|(binary==1.)):
            raise ValueError('HYBRID_FINAL_LITERAL_INTEGER_GATE_FAILED:'+label)
    replay=validate_candidate(case,point)
    if not replay.get('PASS'):raise ValueError('HYBRID_FINAL_ORIGINAL_PHYSICAL_UB_REPLAY_FAILED')
    def objective(d,x):
        return F(float(d['constant']))+sum((F(float(d['objective'][j]))*F(float(x[j]))
            for j in np.flatnonzero(d['objective'])),F(0))
    exact=objective(case.d,point)
    if exact!=objective(case.original_d,original):raise ValueError('HYBRID_FINAL_EXACT_OBJECTIVE_TRANSPORT_DRIFT')
    return dict(PASS=True,exact_Global_UB=str(exact),Global_UB=_display_bound(exact,lower=False),
        point_path=str(path),point_file_sha256=sha256(raw).hexdigest(),point_vector_sha256=vector_sha(point),
        strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=replay,Native_optimize_calls=0)


def _ledger(receipt,case_sha):
    _case_bind(receipt,case_sha)
    if receipt.get('case_sha')!=case_sha or receipt.get('inflight') is not None:
        raise ValueError('HYBRID_FINAL_LEDGER_CASE_OR_INFLIGHT_DRIFT')
    def parameters(value):
        return isinstance(value,dict) and value==EXPECTED_PARAMETERS and not any(isinstance(q,bool) for q in value.values())
    if (receipt.get('allocations')!=ALLOCATIONS or receipt.get('pilot_native_limit_seconds')!=2700.
            or receipt.get('original_M1_native_ceiling_seconds')!=5400.
            or not parameters(receipt.get('parameters'))):
        raise ValueError('HYBRID_FINAL_LEDGER_PREREGISTRATION_DRIFT')
    if any(receipt.get(k) is not False for k in ('memory_limits','memory_automatic_stop','historical_ledgers_modified')):
        raise ValueError('HYBRID_FINAL_FORBIDDEN_LEDGER_POLICY')
    if receipt.get('budget_transfers')!=[]:raise ValueError('HYBRID_FINAL_UNREGISTERED_BUDGET_TRANSFER')
    costs=dict.fromkeys(ALLOCATIONS,0.)
    exact=dict.fromkeys(ALLOCATIONS,F(0))
    wall=0.
    for row in receipt.get('calls',[]):
        if (row.get('case_sha')!=case_sha or row.get('track') not in costs
                or row.get('state') not in ('FINISHED','FAILED') or row.get('runtime_unavailable') is not False
                or not parameters(row.get('parameters'))):
            raise ValueError('HYBRID_FINAL_UNMEASURED_OR_UNFINISHED_NATIVE_CALL')
        q=row.get('Native_Runtime');w=row.get('optimize_wall_seconds')
        if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 for v in (q,w)):
            raise ValueError('HYBRID_FINAL_NONFINITE_NATIVE_ACCOUNTING')
        if row.get('measured_Native_Runtime')!=q:raise ValueError('HYBRID_FINAL_RESERVED_RUNTIME_NOT_MEASURED')
        costs[row['track']]+=q;exact[row['track']]+=F(q);wall+=w
        if sum(exact.values(),F(0))>2700 or any(exact[k]>ALLOCATIONS[k] for k in costs):
            raise ValueError('HYBRID_FINAL_NATIVE_BUDGET_EXCEEDED')
    total=sum(r['Native_Runtime'] for r in receipt.get('calls',[]))
    if costs!=receipt.get('track_Runtime') or total!=receipt.get('Native_Runtime_sum'):
        raise ValueError('HYBRID_FINAL_RUNTIME_SUM_DRIFT')
    return dict(PASS=True,Native_Runtime_sum=total,track_Runtime=costs,
        native_optimize_wall_seconds=wall,failed_calls_counted=sum(r['state']=='FAILED' for r in receipt.get('calls',[])),
        Native_optimize_calls=0)


def _bind_native_receipts(value,calls):
    """Any presented Native evidence must also be charged in this run ledger."""
    if isinstance(value,dict):
        if {'Native_Runtime','track','label','state'}<=set(value) and value not in calls:
            raise ValueError('HYBRID_FINAL_NATIVE_RECEIPT_NOT_IN_CURRENT_LEDGER')
        for child in value.values():_bind_native_receipts(child,calls)
    elif isinstance(value,(list,tuple)):
        for child in value:_bind_native_receipts(child,calls)


def _pricing_round(case,decomp,path,evidence,*,expected_source,expected_result,output,tag):
    result=_json(path/'PRICING_RESULT.json',evidence);_case_bind(result,case.case_sha)
    if result.get('case_sha')!=case.case_sha:raise ValueError('HYBRID_FINAL_PRICING_CASE_MISSING')
    if result!=expected_result:raise ValueError('HYBRID_FINAL_NATIVE_RESULT_PRICING_BINDING_DRIFT')
    identity=_json(path/'PRICE_IDENTITY.json',evidence);_case_bind(identity,case.case_sha)
    if result.get('prices')!=identity:raise ValueError('HYBRID_FINAL_PRICE_IDENTITY_BINDING_DRIFT')
    files=identity['files']
    source=_dual(_packet(files['SOURCE_FULL_DUAL_EXACT.json'],path/'SOURCE_FULL_DUAL_EXACT.json',evidence),case.A.shape[0])
    if source!=_dual(expected_source,case.A.shape[0]):raise ValueError('HYBRID_FINAL_PRICE_SOURCE_ORIGIN_DRIFT')
    coupling=_packet(result['coupling_dual'],path/'COUPLING_DUAL_EXACT.json',evidence)
    _packet(files['COUPLING_DUAL_EXACT.json'],path/'COUPLING_DUAL_EXACT.json',evidence)
    _case_bind(coupling,case.case_sha)
    if (coupling.get('case_sha')!=case.case_sha or not np.array_equal(coupling['original_rows'],decomp.coupling_rows)
            or not np.array_equal(coupling['original_senses'],case.d['sense'][decomp.coupling_rows])):
        raise ValueError('HYBRID_FINAL_COUPLING_ORIGINAL_AXIS_DRIFT')
    lam=_dual(coupling['multipliers'],len(decomp.coupling_rows))
    if lam!=_project(source,decomp.coupling_rows):raise ValueError('HYBRID_FINAL_COUPLING_SOURCE_PROJECTION_DRIFT')
    rhs=sum((F(q)*F(float(case.d['rhs'][decomp.coupling_rows[int(k)]])) for k,q in lam.items()),F(0))
    if rhs!=F(coupling['weighted_rhs_exact']):raise ValueError('HYBRID_FINAL_COUPLING_RHS_DRIFT')
    nonunit=_dual(_packet(result['seed_nonunit_dual'],path/'SEED_NONUNIT_DUAL_EXACT.json',evidence),len(decomp.nonunit_block.original_rows))
    _packet(files['SEED_NONUNIT_DUAL_EXACT.json'],path/'SEED_NONUNIT_DUAL_EXACT.json',evidence)
    if nonunit!=_project(source,decomp.nonunit_block.original_rows):raise ValueError('HYBRID_FINAL_NONUNIT_SOURCE_PROJECTION_DRIFT')
    selected=_packet(result['selected_unit_duals'],path/'SELECTED_UNIT_DUALS_EXACT.json',evidence)
    if set(selected)!=set(decomp.units):raise ValueError('HYBRID_FINAL_UNIT_DUAL_COVER_INCOMPLETE')
    provenance={}
    for unit,block in decomp.units.items():
        seed_name=unit+'_SEED_DUAL_EXACT.json'
        seed=_dual(_packet(files[seed_name],path/seed_name,evidence),len(block.original_rows))
        if seed!=_project(source,block.original_rows):raise ValueError('HYBRID_FINAL_UNIT_SEED_ORIGIN_DRIFT')
        chosen=_dual(selected[unit],len(block.original_rows));selected[unit]=chosen
        individual=_dual(_json(path/(unit+'_SELECTED_DUAL_EXACT.json'),evidence),len(block.original_rows))
        if chosen!=individual:raise ValueError('HYBRID_FINAL_SELECTED_UNIT_PACKET_DISAGREES')
        candidates=[r for r in result['records'] if r.get('unit')==unit and r.get('kind')=='LP']
        if len(candidates)!=1:raise ValueError('HYBRID_FINAL_LOCAL_LP_RECORD_COVER_DRIFT')
        record=candidates[0];_case_bind(record,case.case_sha)
        fresh=None
        if 'dual_evidence' in record:
            packet=record['dual_evidence'];dualpath=path/(unit+'_LP_DUAL.npz')
            if _under(packet['path'],ROOT,'LP_DUAL')!=dualpath.resolve():raise ValueError('HYBRID_FINAL_LP_EVIDENCE_PATH_DRIFT')
            raw=_raw(dualpath,evidence,packet['sha256'])
            with np.load(io.BytesIO(raw),allow_pickle=False) as z:
                if not verify._same(z['original_rows'],block.original_rows) or not verify._same(z['original_columns'],block.original_columns):
                    raise ValueError('HYBRID_FINAL_LOCAL_LP_ORIGINAL_AXIS_DRIFT')
                pi=z['raw_dual'].copy();checked=z['dual'].copy()
            if any(v.dtype!=np.dtype('float64') or v.shape!=(block.A.shape[0],) or not np.isfinite(v).all() for v in (pi,checked)):
                raise ValueError('HYBRID_FINAL_LOCAL_LP_RAW_DUAL_DRIFT')
            invalid=((block.d['sense']=='<')&(pi>0))|((block.d['sense']=='>')&(pi<0))
            repaired=pi.copy();repaired[invalid]=0.
            if not verify._same(repaired,checked):raise ValueError('HYBRID_FINAL_LOCAL_LP_SIGN_REPAIR_DRIFT')
            fresh={str(int(i)):str(F(float(checked[i]))) for i in np.flatnonzero(checked)}
        if chosen!=seed and chosen!=fresh:raise ValueError('HYBRID_FINAL_SELECTED_DUAL_HAS_NO_SOURCE_PACKET')
        provenance[unit]='SIGNED_RAW_LOCAL_LP_PI' if fresh is not None and chosen==fresh else 'PRESERVED_EXACT_SEED'
    proof=verify.verify_global_lagrangian_bound(case,decomp,lam,selected,nonunit_dual=nonunit)
    claimed=result['exact_global_certificate']['exact_bound']
    if F(claimed)!=F(proof['exact_Global_LB']):raise ValueError('HYBRID_FINAL_PRODUCER_BOUND_DISAGREES_WITH_REPLAY')
    dual=proof.pop('canonical_sparse_original_row_rational_dual')
    dualpath=output/(tag+'_INDEPENDENT_ORIGINAL_GLOBAL_DUAL_EXACT.json');_write(dualpath,dual)
    proof['assembled_original_dual_evidence']=dict(path=str(dualpath),sha256=sha256(dualpath.read_bytes()).hexdigest())
    proof['selected_dual_source_provenance']=provenance
    return proof,selected


def _rmp_duals(case,decomp,run_path,result,evidence):
    """Recompute original row/Pi and convexity/Pi mappings from the raw packet."""
    path=run_path/'rmp';rmp=result['RMP']
    full=_json(path/'RMP_ORIGINAL_ROW_DUAL_EXACT.json',evidence)
    eta=_json(path/'RMP_CONVEXITY_DUAL_EXACT.json',evidence)
    receipt=_json(path/'RMP_RESULT.json',evidence);_case_bind(receipt,case.case_sha)
    identity=_json(path/'RMP_IDENTITY.json',evidence);_case_bind(identity,case.case_sha)
    if receipt.get('case_sha')!=case.case_sha or receipt!=rmp or identity!=receipt.get('identity'):
        raise ValueError('HYBRID_FINAL_RMP_CASE_OR_RESULT_BINDING_DRIFT')
    source_rows=np.sort(np.concatenate((decomp.nonunit_block.original_rows,decomp.coupling_rows)))
    if not np.array_equal(identity['source_rows'],source_rows) or not np.array_equal(identity['nonunit_columns'],decomp.nonunit_columns):
        raise ValueError('HYBRID_FINAL_RMP_ORIGINAL_ROW_OR_COLUMN_MAPPING_DRIFT')
    raw=_raw(path/'RMP_RAW_DUAL.npz',evidence)
    with np.load(io.BytesIO(raw),allow_pickle=False) as z:
        if z.files!=['dual','source_rows'] or not verify._same(z['source_rows'],source_rows):
            raise ValueError('HYBRID_FINAL_RMP_RAW_ORIGINAL_ROW_AXIS_DRIFT')
        pi=z['dual'].copy()
    if pi.dtype!=np.dtype('float64') or pi.shape!=(len(source_rows)+len(decomp.units),) or not np.isfinite(pi).all():
        raise ValueError('HYBRID_FINAL_RMP_RAW_PI_AXIS_OR_FINITE_DRIFT')
    signed=pi[:len(source_rows)].copy();senses=case.d['sense'][source_rows]
    invalid=((senses=='<')&(signed>0))|((senses=='>')&(signed<0));signed[invalid]=0.
    reconstructed={str(int(i)):str(F(float(q))) for i,q in zip(source_rows,signed) if q}
    reconstructed_eta={u:str(F(float(pi[len(source_rows)+j]))) for j,u in enumerate(decomp.units)}
    if (reconstructed!=_dual(full,case.A.shape[0]) or reconstructed!=_dual(rmp['full_original_dual'],case.A.shape[0])
            or eta!=reconstructed_eta or rmp.get('convexity_duals')!=reconstructed_eta):
        raise ValueError('HYBRID_FINAL_RMP_RAW_PI_RATIONAL_MAPPING_DRIFT')
    return reconstructed,reconstructed_eta


def verify_run(run_path,output=REPORTS,*,case=None):
    """Return/write checked scientific facts, preserving partial/error status.

    A missing optional RMP round is NOT_RUN. A malformed attempted certificate
    is an error, while the completed historical bound remains available. No
    new goal or stage completion is inferred from metadata or solver statuses.
    """
    begin=perf_counter();run_path=_under(run_path,RUNTIME,'RUN');output=_output(output)
    report=dict(schema='V42_M1_FAST_HYBRID_INDEPENDENT_FINAL_V1',PASS=False,
        case_sha=None,run_id=run_path.name,run_path=str(run_path),status='NOT_COMPLETED',
        final_exact_UB=None,final_exact_LB=None,final_UB=None,final_LB=None,gap=None,
        UB_gain=None,LB_gain=None,pricing_certificates={},
        rmp_pricing_closure=dict(status='NOT_RUN',full_unit_missing_column_pricing_closure_certified=False),
        issues=[],source_evidence_sha256={},Native_optimize_calls=0,
        historical_reports_modified=False,Native_outputs_modified=False,
        restricted_RMP_or_MIP_native_bound_used_as_Global_LB=False,M1_ACCEPTED=False,P2_certificate=None)
    evidence=report['source_evidence_sha256'];issues=report['issues']
    def failure(phase,exc):issues.append(dict(phase=phase,error=type(exc).__name__+': '+str(exc)))
    try:
        case=load_case_read_only() if case is None else case
        report['case_sha']=case.case_sha;phase0=verify.phase0(case);report['phase0']=phase0
        report['final_exact_LB']=phase0['exact_Global_LB'];report['final_exact_UB']=phase0['exact_Global_UB']
        baseline_lb,baseline_ub=F(report['final_exact_LB']),F(report['final_exact_UB'])
        decomp=build_blocks(case);report['independent_partition']=verify.verify_decomposition(case,decomp)
        ledger=_json(run_path/'NATIVE_RUNTIME_LEDGER.json',evidence);_case_bind(ledger,case.case_sha)
        if ledger.get('case_sha')!=case.case_sha:raise ValueError('HYBRID_FINAL_LEDGER_CASE_MISMATCH')
        if ledger.get('inflight') is not None:
            report['status']='NATIVE_STILL_IN_FLIGHT_NO_CURRENT_CERTIFICATE_ADMITTED'
            raise RuntimeError('POST_NATIVE_VERIFICATION_REQUIRES_NATURAL_COMPLETION')
        result=_json(run_path/'NATIVE_PHASE_RESULTS.json',evidence);_case_bind(result,case.case_sha)
        if (result.get('case_sha')!=case.case_sha or result.get('run_id')!=run_path.name
                or _under(result.get('run_path',''),RUNTIME,'RESULT_RUN')!=run_path):
            raise ValueError('HYBRID_FINAL_RESULT_RUN_BINDING_DRIFT')
        prereg=_json(run_path/'PREREGISTRATION.json',evidence);_case_bind(prereg,case.case_sha)
        if prereg.get('run_id')!=run_path.name or prereg.get('baseline_completed_HEAD')!=verify.BASE_HEAD:
            raise ValueError('HYBRID_FINAL_PREREGISTERED_RUN_OR_HEAD_DRIFT')
        report['ledger_verification']=_ledger(ledger,case.case_sha)
        if result.get('ledger')!=ledger:raise ValueError('HYBRID_FINAL_RESULT_LEDGER_BINDING_DRIFT')
        _bind_native_receipts(result,ledger['calls'])
        protected=_json(run_path/'BASELINE_PROTECTION.json',evidence)
        executed=_json(run_path/'EXECUTED_SOURCE_HASHES.json',evidence)
        for catalog in (protected,executed):
            for name,expected in catalog.items():
                if name in ('README.md','.gitattributes'):continue
                _raw(_under(ROOT/name,ROOT,'PROTECTED_SOURCE'),evidence,expected)
        report['source_and_historical_protection']=dict(PASS=True,protected_files=len(protected),executed_files=len(executed))
        report['Native_execution_errors_preserved']=result.get('errors',[])
        try:
            ub=_strict_ub(case,run_path/'FINAL_STRICT_UB_POINT.npz',evidence);report['strict_UB_certificate']=ub
            expected=result.get('UB',{}).get('strict_final_replay',{}).get('point_sha256')
            if expected is not None and expected!=ub['point_vector_sha256']:raise ValueError('HYBRID_FINAL_UB_RESULT_POINT_BINDING_DRIFT')
            if F(ub['exact_Global_UB'])>baseline_ub:raise ValueError('HYBRID_FINAL_STRICT_UB_REGRESSED_FROM_PRESERVED_SEED')
            report['final_exact_UB']=ub['exact_Global_UB']
        except Exception as exc:failure('FINAL_STRICT_UB',exc)
        original=json.loads(verify._committed(verify.PREVIOUS+'artifacts/C3A_REPAIRED_RATIONAL_DUAL.json'))
        for name,path,source in [('initial',run_path/'pricing_initial',original),
                                  ('rmp',run_path/'pricing_rmp',result.get('RMP',{}).get('full_original_dual'))]:
            if source is None:
                report['pricing_certificates'][name]=dict(status='NOT_RUN_NO_FINITE_RMP_ORIGINAL_ROW_PI')
                continue
            if name=='rmp' and not (path/'PRICING_RESULT.json').is_file():
                if result.get('RMP_PRICING',{}).get('status','').startswith('NOT_RUN'):
                    report['pricing_certificates'][name]=dict(status='NOT_RUN_PREREGISTERED_CONDITION')
                    continue
            try:
                if name=='rmp':
                    full,eta=_rmp_duals(case,decomp,run_path,result,evidence)
                    if full!=_dual(source,case.A.shape[0]):raise ValueError('HYBRID_FINAL_RMP_PRICE_ORIGIN_DRIFT')
                proof,selected=_pricing_round(case,decomp,path,evidence,expected_source=source,
                                               expected_result=result['PRICING' if name=='initial' else 'RMP_PRICING'],
                                               output=output,tag=run_path.name+'_'+name.upper())
                report['pricing_certificates'][name]=proof
                report['final_exact_LB']=str(max(F(report['final_exact_LB']),F(proof['exact_Global_LB'])))
                if name=='rmp':
                    report['rmp_pricing_closure']=verify.verify_rmp_pricing_lower_bounds(case,decomp,
                        dict(case_sha=case.case_sha,multipliers=source),selected,eta)
            except Exception as exc:
                failure(name.upper()+'_PRICING_CERTIFICATE',exc)
                report['pricing_certificates'][name]=dict(status='NOT_ADMITTED_INDEPENDENT_REPLAY_FAILED')
        if not issues:
            report['PASS']=True;report['status']='COMPLETED_RUN_INDEPENDENT_SCIENTIFIC_REPLAY_PASS'
    except Exception as exc:failure('RUN_ADMISSION',exc)
    if report['final_exact_LB'] is not None and report['final_exact_UB'] is not None:
        try:
            lb,ub=F(report['final_exact_LB']),F(report['final_exact_UB'])
            report.update(final_LB=_display_bound(lb,lower=True),final_UB=_display_bound(ub,lower=False),gap=verify.target_thresholds(lb,ub),
                          LB_gain=float(lb-baseline_lb),UB_gain=float(baseline_ub-ub),
                          exact_LB_gain=str(lb-baseline_lb),exact_UB_gain=str(baseline_ub-ub))
        except Exception as exc:failure('EXACT_GAP_ARITHMETIC',exc);report['PASS']=False
    report['M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED']=bool(report['PASS'] and report['gap'] and
        report['gap']['M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED'])
    report['checker_wall_seconds']=perf_counter()-begin
    _write(output/'INDEPENDENT_FINAL_VERIFICATION.json',report)
    return report
