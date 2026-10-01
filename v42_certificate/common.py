from pathlib import Path
import csv,gzip,hashlib,json,subprocess,time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_late_window_certificate_mipstart'
PRIOR=ROOT/'docs/v42_m1_integrality_gap_root_cause'
LOCAL=ROOT.parent/'V42_CERTIFICATE_LOCAL'
BASE='c90525c330c2f8aa9971030b87cf154ecf1b284f'
F3=.5718494602017812
S2=.5722125039436496
START_UB=.5912812634331275
OLD_UB=.6696147314213984
TOL=1e-5
OBJ_TOL=1e-7
MATERIAL=.001
WINDOWS={'B1':[66,95],'B2':[66,95],'B3':[58,95]}
SETTINGS=dict(Method=2,NodeMethod=1,Threads=4,Seed=20260929,MIPFocus=1,
              Heuristics=.1,DegenMoves=0,CutPasses=1,MIPGap=0.,MIPGapAbs=.0005,
              TimeLimit=1800.)

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def dump(name,v):
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/name;tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def table(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT).decode().strip()
def selected_arc(a,w):return a[1]<=w[1] and a[3]>w[0] or w[0]<=a[1]<=w[1]
def restore(n,kind,arm,arcs):
    if kind!='B':return False
    if arm in ['NATIVE_START','PRODUCTION']:return True
    w=WINDOWS[arm]
    if n.startswith('arc['):return selected_arc(arcs[int(n[4:-1].split(',')[1])],w)
    if n.startswith('charge_mode['):return arm!='B1' and w[0]<=int(n[12:-1].split(',')[1])<=w[1]
    raise AssertionError(n)
def inputs():
    # This inherited accessor reads only sealed caches; no inherited output writer is called.
    from v42_forensic.common import inputs as source
    return source()
def arcs():
    from v42_forensic.common import arcs_for
    _,_,_,sites,_,routes,_=inputs();return arcs_for(sites,routes)
def load_axis():
    with np.load(PRIOR/'F3_MODEL_AXIS.npz',allow_pickle=False) as z:return {k:z[k] for k in z.files}
def load_start():
    with np.load(OUT/'MIP_START_EXACT.npz',allow_pickle=False) as z:return z['names'],z['values']
def exact_values(names,source):
    assert len(set(names))==len(names),'DUPLICATE_NATIVE_AXIS'
    missing=[str(n) for n in names if n not in source];assert not missing,('MISSING_NATIVE_START_VALUES',missing[:10])
    values=np.asarray([source[n] for n in names],dtype=float);assert np.isfinite(values).all(),'NONFINITE_START'
    return values
def matrix_validation(m,values):
    v=np.asarray(values);A=m.getA();rhs=np.asarray(m.getAttr('RHS'));sense=np.asarray(m.getAttr('Sense'));r=A@v-rhs
    error=np.where(sense=='=',abs(r),np.where(sense=='<',r,-r))
    row=max(0.,float(error.max()));bound=max(0.,float((np.asarray(m.getAttr('LB'))-v).max()),float((v-np.asarray(m.getAttr('UB'))).max()))
    return dict(PASS=bool(np.isfinite(v).all() and max(row,bound)<=TOL),row_max_violation=row,bound_max_violation=bound)
def original_validation(names,values):
    from v42_forensic.runner import validate_full_plan
    return validate_full_plan(names,values,load_axis()['original_types'])
def interval(lower,upper,status):
    assert lower is None or upper is None or lower<=upper+OBJ_TOL
    width=None if lower is None or upper is None else max(0.,upper-lower)
    positive=lower is not None and lower-S2>=MATERIAL
    negative=upper is not None and upper-S2<=MATERIAL
    return dict(lower=lower,upper=upper,width=width,material=bool(positive),negative_certificate=bool(negative),
        tight_interval=bool(width is not None and width<=MATERIAL),solver_optimal=status==2,
        conclusion='CERTIFIED_MATERIAL' if positive else 'CERTIFIED_NONMATERIAL' if negative else 'INCONCLUSIVE',
        nonmateriality_reference='S2 certified original-M1 LB',gain_lower_vs_S2=None if lower is None else lower-S2,
        gain_upper_vs_S2=None if upper is None else upper-S2,
        proof='Partial optimum lies in [valid partial LB, matrix/domain-validated feasible partial upper]. A tight interval or OPTIMAL status identifies an optimum range; nonmateriality additionally requires its upper-S2<=0.001.')
def incremental(weaker,stronger):
    # Nested integrality sets imply nonnegative optimum differences.
    return dict(lower=max(0.,stronger['lower']-weaker['upper']),upper=max(0.,stronger['upper']-weaker['lower']),
        exact_optima_required=False,formula='max(0,L_stronger-U_weaker) <= opt_stronger-opt_weaker <= U_stronger-L_weaker')
def choose_case(certs):
    if certs['B1']['material']:return 'CASE_A_ROUTE_INTEGRALITY_MATERIAL'
    mode=incremental(certs['B1'],certs['B2']);buffer=incremental(certs['B2'],certs['B3'])
    if mode['lower']>=MATERIAL:return 'CASE_B_MODE_INCREMENT_MATERIAL'
    if buffer['lower']>=MATERIAL:return 'CASE_C_INTERTEMPORAL_INCREMENT_MATERIAL'
    if all(c['negative_certificate'] for c in certs.values()):return 'CASE_D_PARTIAL_NONMATERIAL_SEARCH_QUALITY_NEXT'
    return 'CASE_E_INCONCLUSIVE'
def next_certificate_arm(certs,executed):
    if 'B3' not in executed:return 'B3'
    if not certs['B3']['material']:return None
    if 'B2' not in executed:return 'B2'
    if not certs['B2']['material']:return None
    return 'B1' if 'B1' not in executed else None

def setup():
    assert git('rev-parse','HEAD')==BASE and not (OUT/'PREREGISTRATION.json').exists()
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(exist_ok=True)
    files=git('ls-files').splitlines()
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base_head=BASE,files=[dict(path=n,sha256=sha(ROOT/n)) for n in files]))
    dump('PR112_BASE_RECEIPT.json',dict(BASE_PR=112,BASE_HEAD=BASE,branch=git('branch','--show-current'),
        inherited_evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(PRIOR.rglob('*')) if p.is_file()]))
    dump('PREREGISTRATION.json',dict(BASE_PR=112,BASE_HEAD=BASE,created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        scope=[1,2,3,4,5,6,8,13],excluded=[7,9,10,11,12],model='Exact original sparse F3 rows/bounds/objective; binary-subset relaxation only',
        windows=WINDOWS,reference_LB=S2,F3_LB=F3,validated_start_UB=START_UB,physical_tolerance=TOL,objective_tolerance=OBJ_TOL,
        strategy_candidates=1,solver=SETTINGS,GPU=False,custom_cuts=False,parameter_sweep=False,
        strategy_rationale='Inherited arms spent 278-503s in root barrier/crossover, then stayed at the root during degenerate moves/cut passes. Keep Method=2; four threads support parallel barrier/root helpers, DegenMoves=0 and CutPasses=1 avoid repeated root-only work; MIPFocus=1/Heuristics=0.1 seek the partial feasible upper needed for a negative certificate. This is a preregistered joint strategy, not an attribution comparison of individual parameter effects.',
        comparison_to_PR112=dict(Threads='1 -> 4; one solve at this setting, no sweep',MIPFocus='3 -> 1',Heuristics='0 -> 0.1',DegenMoves='-1 -> 0',CutPasses='-1 -> 1',MIPGap='0.005 -> 0',MIPGapAbs='default -> 0.0005',TimeLimit='600 -> 1800 optimize-only, with certificate-driven early stop'),
        stops=dict(positive='BestBd >= S2+0.001+1e-7',negative='feasible partial objective <= S2+0.001-1e-7',tight='MIPGapAbs=0.0005',timeout='INCONCLUSIVE unless a separately validated certificate exists'),
        native_acceptance_probe=dict(TimeLimit=30,SolutionLimit=1,Heuristics=0,complete_original_binary_model=True,production=False),
        certificates='Never use S2 as a lower bound on the weaker partial optimum. Partial interval LB=max(inherited F3 LP LB, this arm BestBd); S2 is an original-M1 reference/global LB. Nonmaterial iff validated partial upper-S2<=0.001. Every partial BestBd is a valid original-M1 LB.',
        inclusion='F_original_integer subset F_B3 subset F_B2 subset F_B1 subset F_F3. Stronger feasible uppers transfer to weaker models; weaker lower bounds transfer to stronger models, after exact unchanged-row/domain checks.',
        production=dict(max_runs=1,TimeLimit=1800,MIPGap=.005,gate='native start accepted AND all B1/B2/B3 have positive material or negative nonmaterial certificates AND case != E; original full domain/physics only'),
        P2_gate='Only independently accepted production P1 with global implied gap<=0.005; original MIN_INTERVENTION movement-energy then movement-count tuple and P1 lock',
        A1_S1_S2_S3_optimize_calls=0,terminal_counterfactual_rerun=False,no_new_remedy=True,downstream=False,
        official_parameters='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html',
        official_MIP_start='https://docs.gurobi.com/projects/examples/en/current/overview/starts.html'))
    print('PREREGISTRATION SEALED',flush=True)
if __name__=='__main__':setup()
