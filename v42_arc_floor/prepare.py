"""No optimize: exact FULL matrix relaxation identity and preregistration."""
from .common import *
import numpy as np

def identity(A,d,model):
    from v42_integrated.matrix import arrays
    from v42_degen.identity import signature,digest
    B,e=arrays(model)
    assert np.array_equal(A.indptr,B.indptr) and np.array_equal(A.indices,B.indices) and np.array_equal(A.data,B.data)
    for k in ('names','rhs','sense','lower','upper','objective','constant'):assert np.array_equal(d[k],e[k]),k
    assert np.all(e['types']=='C') and model.ModelSense==1 and not model.IsMIP
    return dict(PASS=True,rows=model.NumConstrs,columns=model.NumVars,nnz=model.NumNZs,matrix_signature=signature(B,e),row_axis_SHA=digest(d['row_names']),column_axis_SHA=digest(d['names']),native_row_axis_SHA=digest(e['row_names']),discrete_relaxed=int((d['types']!='C').sum()),binary_relaxed=int((d['types']=='B').sum()),integer_relaxed=int((d['types']=='I').sum()),only_integrality_relaxed=True,all_types_continuous=True,all_original_LB_UB_exact=True,ObjCon=model.ObjCon,ModelSense=model.ModelSense,IsMIP=False)

def prepare():
    import gurobipy as gp
    from v42_degen.identity import inputs,signature,digest
    from v42_dw_root.models import build,hash_column
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();assert head==BASE_HEAD
    pr=json.loads(subprocess.check_output(['gh','pr','view','143','--repo','BeaverVillage/MobileESS','--json','headRefOid,isDraft'],text=True));assert pr['headRefOid']==head and pr['isDraft']
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');write('PR143_BYTE_FREEZE.json',dict(head=head,files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked if p]))
    for name in ('logs','pricing_points','pricing_receipts','columns','bound_certificates'):(OUT/name).mkdir(exist_ok=True)
    previous=read(DOMINANCE/'VERIFICATION.json');assert previous['PASS'] and read(DOMINANCE/'DW_FULL_SCALE_DOMINANCE_PROOF.json')['PASS']
    checks=[]
    for directory,h in old_columns():
        file=directory/h['file'];assert sha(file)==h['file_SHA']
        with np.load(file) as z:
            new='x' in z;x=z['x'] if new else z['local_values'];a=z['a'] if new else z['master_coefficients'];c=float(z['c'] if new else z['objective']);assert hash_column(x,a,c)==h['SHA256']
        checks.append(dict(file=file.relative_to(ROOT).as_posix(),file_SHA=h['file_SHA'],column_SHA=h['SHA256'],MESS=h['MESS']))
    assert len(checks)==1158
    A,d,B,e,oldid,freeze=inputs();original=gp.read(str(SOURCE/'FULL.mps'));original.Params.LogToConsole=0
    constructs=dict(SOS=original.NumSOS,general_constraints=original.NumGenConstrs,quadratic_constraints=original.NumQConstrs,quadratic_objective_terms=original.NumQNZs)
    assert not any(constructs.values()),'UNREPRESENTED_NONLINEAR_SOS_GENERAL_INDICATOR_STOP'
    # Validate original MPS numeric payload before using relax() as corroboration.
    from v42_integrated.matrix import arrays
    M,f=arrays(original);assert signature(M,f)==signature(A,d)
    relaxed=dict(d,types=np.full(A.shape[1],'C',dtype=d['types'].dtype))
    native=build(A,relaxed,'FROZEN_ORIGINAL_ARC_LP');result=identity(A,d,native)
    assert np.array_equal(native.getAttr('ConstrName'),d['row_names'])
    helper=original.relax();helper.update();cross=identity(A,d,helper)
    result.update(native_relax_independent_crosscheck=cross,original_native_constructs=constructs,original_matrix_SHA=sha(SOURCE/'FULL_A.npz'),original_attributes_SHA=sha(SOURCE/'FULL_DATA.npz'),original_types_SHA=digest(d['types']),relaxed_types_SHA=digest(relaxed['types']),original_signature=signature(A,d),native_helper_row_aliases='Original MPS row names may be aliases; coefficients, ordered row axis/RHS/senses, and all column attributes match. Direct matrix LP preserves the authoritative FULL_DATA row names.',no_DW_columns=True,no_RMP=True)
    write('ARC_LP_RELAXATION_IDENTITY.json',result)
    np.savez_compressed(OUT/'ARC_LP_RELAXATION_MAP.npz',original_types=d['types'],relaxed_types=relaxed['types'],discrete_indices=np.flatnonzero(d['types']!='C'))
    native.dispose();helper.dispose();original.dispose()
    with np.load(SOURCE/'REDUCTION_AXES.npz') as z:keep=z['keep']
    with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:pairs=z['binding_row_column']
    fullpairs=np.column_stack((keep[pairs[:,0]],pairs[:,1]));np.savez_compressed(OUT/'ARC_ORIGINAL_EQUALITY_PIVOTS.npz',row_column=fullpairs)
    write('ARC_LP_BASE_IDENTITY.json',dict(PASS=True,PR143_exact_head=head,remote=pr,original_identity=oldid,matrix_signature=signature(A,d),A1_freeze=freeze,retained_columns=1158,checks=checks,checkpoint_SHA=sha(DOMINANCE/'DW_CHECKPOINT_LATEST.json'),dominance_proof_SHA=sha(DOMINANCE/'DW_FULL_SCALE_DOMINANCE_PROOF.json'),coupling_proof_SHA=sha(DOMINANCE/'DW_COUPLING_IDENTITY_AUDIT.json'),all_PR143_tracked_bytes_frozen=True,repeated_physical_audit='Reuse immutable PR143 full 1158-column original-row/physical audit; all bytes and hashes checked again.',old_pricing_replayed=False))
    write('ARC_LP_PREREGISTRATION.json',dict(base=head,arc_optimize_budget_seconds=600,arc_budget_includes_tiny_sign_fixtures=True,optional_second_LP=False,CG_optimize_budget_seconds=900,budgets_separate=True,automatic_extension=False,primary_LP=dict(Threads=1,Method=2,Crossover=0,PreDual=0,BarConvTol=1e-11,FeasibilityTol=EPS,OptimalityTol=EPS,TimeLimit='600 minus already consumed native sign-fixture time and safety margin'),primary_method_reason='Single-thread barrier without crossover, the original pure LP method with complete original-axis X/Pi/RC; exact rational equality-multiplier repair handles stationarity residual. No MIP parameter, no algorithm sweep.',matrix_SHA=sha(SOURCE/'FULL_A.npz'),attributes_SHA=sha(SOURCE/'FULL_DATA.npz'),relaxation_map_SHA=sha(OUT/'ARC_LP_RELAXATION_MAP.npz'),certificate='Exact Fraction sign-valid Lagrangian bound over original LB/UB only. Reverse original triangular binding equalities repair free-coordinate stationarity in equality multipliers; original matrix unchanged. A required infinite interval endpoint with nonzero coefficient invalidates the certificate. Never use pseudo-finite infinity or incumbent/MIP BestBd.',certificate_numerical_gate=dict(affine=POST,bounds=EPS,objective_agreement=EPS,dual_support_le_primal_tolerance=EPS,desirable_primal_dual_gap=1e-7),threshold_reference='Native terminal OPTIMAL original arc objective plus exact 1/200. Also store certified floor plus1/200; outward max/min of both thresholds for material/nonmaterial respectively, preventing a decision inside numerical uncertainty band.',Discovery_rounds_max=8,Discovery_cap=20,Certification_cap=90,Certification_rounds_max=1,early_triggers=['two consecutive zero accepted','last3 completed rounds total upper decrease < 0.001','U minus official T <= 0.002','budget cannot reserve next Discovery + post RMP + final certification'],fixed_pricing_workers=4,pricing_Threads=1,RAM_floor_GiB=1,hard_stops=['OOM','commit >=95%','PR142 sustained hard paging + pagefile growth','solver/license/model failure'],multi_columns_per_MESS=4,warm_RMP_selected=False,warm_tests=False,adaptive_smoothing='Unchanged PR142 next_smoothing_weight; restore center and alpha0.125 only if exact pool+row+dual axis identity, otherwise true current center/alpha0.125',true_RC_acceptance=DISCOVERY_RC,no_negative_BestBd=-EPS,pricing_full_original_domain=True,pricing_redesign=False,column_deletion=False,parameter_sweeps=False,May_production=[0,0,0],Branch_and_Price=False))
    write('CAMPAIGN_WORKER_POLICY.json',dict(B0_DAY_WORKERS=4,B1_DAY_WORKERS=1,B2_DAY_WORKERS=4,B3_DAY_WORKERS=1,days_per_arm=31,Threads=1,B2_INNER_PRICING=1,B3_INNER_PRICING=4,main=['B0','B1','B2','B3(L1)'],after_main=['B3(L2)','B3(L3)','B3(L4)'],Actual_to_Planning=False,previous_Planning_only=True))
    write('CAMPAIGN_NO_EXECUTION_RECEIPT.json',dict(May_optimizer_calls=0,Actual_calls=0,Fresh_AC_calls=0,production_M1=False,P2=False,A2=False,M2=False,Branch_and_Price=False))
    print('ARC_PREREG_IDENTITY_PASS',result['rows'],result['columns'],result['nnz'],result['discrete_relaxed'],flush=True)

def freeze():
    sources=sorted((ROOT/'v42_arc_floor').glob('*.py'))+sorted((ROOT/'tests/v42_arc_floor').glob('*.py'))
    names=['ARC_LP_BASE_IDENTITY.json','ARC_LP_RELAXATION_IDENTITY.json','ARC_LP_PREREGISTRATION.json','CAMPAIGN_WORKER_POLICY.json']
    write('EXECUTION_FREEZE.json',dict(sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sources],preregistrations={n:sha(OUT/n) for n in names},arrays={n:sha(OUT/n) for n in ('ARC_LP_RELAXATION_MAP.npz','ARC_ORIGINAL_EQUALITY_PIVOTS.npz')}))

if __name__=='__main__':
    import sys
    freeze() if '--freeze-only' in sys.argv else prepare()
