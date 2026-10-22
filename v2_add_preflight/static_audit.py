"""Audit original algorithms before any electrical or formulation adaptation."""
import ast, subprocess
from .static_common import *

def audit():
    res=init()
    paths=['v44/worker.py','v44/stages.py','v44/q250_m4.py',
        'v42_may_campaign_native90/m_model.py','v42_supercompact/formulation.py',
        'v42_supercompact/presolve.py','v44/frozen/v43_mess/library.py',
        'v44/frozen/v43_mess/case.py','v44/svr11_ac.py',
        'v44/svr11_frozen/v42_voltage_control/integration.py',
        'v44/svr11_frozen/v42_voltage_control/timecontrol.py']
    sources=[]
    for p in paths:
        b=subprocess.check_output(['git','show',SOURCE+':'+p],cwd=ROOT)
        q=ROOT/p
        blob=subprocess.check_output(['git','hash-object','--path='+p,str(q)],cwd=ROOT,text=True).strip()
        pinned=subprocess.check_output(['git','rev-parse',SOURCE+':'+p],cwd=ROOT,text=True).strip()
        sources.append(dict(relative=p,**record(q),same_as_r043=blob==pinned,
            raw_worktree_bytes_equal=b==q.read_bytes(),git_clean_filter_blob=blob,
            pinned_git_blob=pinned,worktree_EOL_normalization_is_not_algorithm_change=True))
    pin=read(ROOT/'docs/v44/V43_MESS_REUSE_SOURCE_MANIFEST.json')
    external=[]
    for r in pin['sources']:
        q=Path(r['source']['path'])
        if r['scope']=='WHOLE_RUNTIME_ONLY':
            actual=record(q);assert actual['sha256']==r['source']['sha256']
            external.append(dict(module=r['module'],actual=actual,verified_original_SHA=True))
    findings=[
        dict(question='M1/M2 construction order',source='v44/worker.py:m_stage; m_model.py:build_case',
            finding='Original mobility + full grid -> Compact node flow -> Presolve.run -> verify_transport -> prepare_k16 -> original K48 -> optimize_mess/Adaptive Beam/Direct Joint'),
        dict(question='Original static elimination',source='v42_supercompact/presolve.py',
            finding='Exact fixed/singleton values, constant-safe and proportional rows, implied singleton bounds, profitable unit aliases and identical affine auxiliaries. Fraction proof rejects nonrepresentable binary64 substitutions; dense/nonunit pivots retained.'),
        dict(question='K48 case/domain',source='table_v_k48.py:identity/prepare_k16/verify_packet',
            finding='Hashes original_A/original_d, stage/date/source/AIDC anchor. K16 -> K32 -> K48 original pricing; restricted Joint ObjBound never Global LB.'),
        dict(question='Beam rules',source='m_candidates.py:generate; m_adaptive.py:run',
            finding='Original route DAG; STAY and current FULL retained; width12/16, heuristic MOVE depth4, optimistic SOC/terminal tests, SignedMinimax plus JointDispatchScore, feedback/adaptive pools. These are heuristic candidate pools, not deletion of original FULL route domain.'),
        dict(question='Direct Joint constraints',source='m_engine.py:direct_joint',
            finding='Exact route-coordinate lift to per-unit lambda path choices; every retained nonroute row and P/Q/SOC/mode remains joint; charge modes unchanged; FULL replay for every offered UB.'),
        dict(question='New delayed master difference',source='v2_add_preflight/may01_exact_native.py:LiteralMaster',
            finding='Initial431255 rows omit necessary original rows; post-candidate refine/iterate is new Grid CG and prohibited in official route. Retained only as historical diagnostic.'),
        dict(question='Adapter-only work',source='m_model.py; library.py; blocks.py; planning.py',
            finding='Replace feeder axes/coefficients and current-case metadata through isolated adapter. Source contains IEEE123 7Reg/120 transformer and four-unit guards. No original algorithm edits allowed; full adapters must be certified before campaign.')]
    table('ORIGINAL_EXECUTION_PATH_AUDIT.csv',findings)
    put('V44_R043_ALGORITHM_IDENTITY_AUDIT.json',dict(original=SOURCE,baseline=BASE,
        audited_before_new_model_edits=True,sources=sources,external_pinned_algorithms=external,
        algorithm_source_unchanged=all(r['same_as_r043'] for r in sources),findings=findings,
        new_optimizer_created=False,official_campaign_executed=False,resources=res))
    # Hardware selection follows source fidelity and the fixed user scenario,
    # not a new voltage/line-loading search. Previous candidates stay archived.
    hw=dict(experiment='V2_add',day='2025-05-01',beta_BG=2.,candidate='H0_SOURCE_YY',
        Planning='S0 original Reg12/CapControl9',Actual='S1_03 original Reg12 + serial SVR3 (9 single-phase controls)',
        Source_P5_pu=1.04,original_Vreg=123.5,CAPBank3_initial='OFF',
        IDC=read(HISTORY/'SOURCE_YY_PORT_PREREGISTRATION.json'),
        SVR=record(HISTORY/'MAY01_HARDWARE_PREREGISTRATION.json'),
        ports=record(HISTORY/'SOURCE_YY_ALL24_HARDWARE_READBACK.json'),
        source=SOURCE,initial_MESS8=INITIAL,all_arms_same_hardware_and_policy=True,
        frozen_before_new_coefficients=True,physical_certification_pending=True,
        basis='User fixed beta2/SVR3; source Wye/Wye winding fidelity at native8500 MV. No new hardware search or fitted tap/impedance.',
        FIELD_INSTALLATION_UNVERIFIED=True)
    put('SOURCE_YY_HARDWARE_FREEZE.json',dict(**hw,hardware_sha=digest(hw)))
    return findings

if __name__=='__main__':audit()
