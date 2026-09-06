"""Separate lineage; never write into the preserved V40E evidence tree."""
from pathlib import Path
from contextlib import contextmanager
import shutil
from dayahead.paper_analysis.storage import read,write_json,reference,sha,digest

REL=Path('dayahead/artifacts/v40f_min_rho_aidc_correction')
PREVIOUS=Path('dayahead/artifacts/v40e_background_mapping_fix')
REQUEST=Path('C:/Users/kjw39/.codex/attachments/6be86382-11f6-44f5-96d5-6358f5101dfe/pasted-text.txt')
COMMON_REQUEST=Path('C:/Users/kjw39/.codex/attachments/83a3948e-d286-48cd-8b36-da754ec159e7/pasted-text.txt')


def seal_previous(repo):
    repo=Path(repo).resolve();out=repo/REL;out.mkdir(parents=True,exist_ok=True)
    path=out/'PRESERVED_V40E_EVIDENCE_MANIFEST.json'
    if not path.exists():
        paths=sorted((repo/PREVIOUS).rglob('*'))+sorted((repo/'dayahead/v40e').glob('*.py'))
        write_json(path,{'files':{str(p):reference(p) for p in paths if p.is_file()}})
    write_json(out/'V40F_NORMATIVE_CORRECTION_CONTRACT.json',{
        'INTENDED_FORMULATION':'MIN_RHO_AIDC','OLD_IMPLEMENTATION':'ZERO_FEASIBILITY',
        'CORRECTION_TYPE':'IMPLEMENTATION_DEFECT_CORRECTION','classification':'AIDC_OBJECTIVE_IMPLEMENTATION_DEFECT',
        'normative_user_authority':reference(REQUEST),'common_service_user_authority':reference(COMMON_REQUEST),
        'version':'COMMON_SERVICE_V2','supersedes_previous_inference':'C. METHOD_DESIGN_GAP',
        'previous_forensic_evidence_preserved':reference(path),
        'objectives':['MIN corrected Planning rho_max','MIN canonical full-interval UID/site GPU-slot deviation from RW','deterministic stable tie-break'],
        'primary_tolerance':1e-6,'primary_nondegradation_tolerance':1e-6,
        'zero_feasibility_allowed_only':'Fresh feasibility warm start; never final AIDC objective',
        'B0':'RW/reference AIDC, MESS OFF','B1':'MIN_RHO_AIDC, MESS OFF',
        'B2':'Exact B0 RW/reference AIDC, MESS ON','B3':'Exact B1 A0 -> M1 -> A1 -> MF',
        'reference_candidate':'Frozen RW starts/sites/inherited state, evaluated using common causal-safe T_DA. No RW-specific durations.',
        'coordinated_domain':'Inherited A1 authorized_options over the common-duration B0 baseline, no M1 state; RUNNING/WAN fixed',
        'reference_terminal_authority':'Per-job terminal obligation derived once from RW decisions + common T_DA',
        'coordinated_terminal_authority':'Same common B0 per-job terminal obligation; exact post-H profile equality',
        'different_duration_model_candidate_union':'PROHIBITED',
        'reference_infeasibility':'FAIL_CLOSED with exact job/constraint; no new reference schedule',
        'no_new_flexibility_in_coordinated_domain':True,'May_result_parameter_tuning':False,
        'MESS_P':0,'MESS_Q':0,'MESS_mobility_decisions':None,
        'B2_B3_AUTHORIZED':'NO','FULL_MAY_AUTHORIZED':'NO','UNASSIGNED_44_case_blocker':'PRESERVED'})
    return out


@contextmanager
def electrical_namespace():
    from dayahead.v40e import electrical
    old=electrical.REL;electrical.REL=REL;electrical.upstream.cache_clear()
    try:yield electrical
    finally:electrical.REL=old;electrical.upstream.cache_clear()


def rebuild(repo):
    repo=Path(repo).resolve();out=seal_previous(repo)
    # April gradients were already remeasured with the corrected mapping and
    # unchanged frozen April selection. Their source SHAs are retained verbatim.
    target=out/'april_joint_authority';target.mkdir(exist_ok=True)
    for src in (repo/PREVIOUS/'april_joint_authority').iterdir():
        if src.is_file():
            dst=target/src.name
            if not dst.exists():shutil.copyfile(src,dst)
            assert sha(src)==sha(dst)
    with electrical_namespace() as electrical:
        electrical.rebuild_day(repo,'2025-05-01')
        c=electrical.planning_context(repo,'2025-05-01')
        import numpy as np
        from dayahead.paper_analysis.storage import write_npz
        arrays={'node_names':np.array(c.nodes),'branch_names':np.array(c.coefficients[0].branch_names)}
        for field in ('voltage_constant','voltage_matrix','current_constant','current_matrix','flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix','branch_limits'):
            arrays[field]=np.array([getattr(x,field) for x in c.coefficients])
        write_npz(out/'electrical/2025-05-01/V40F_PLANNING_ELECTRICAL_COEFFICIENTS.npz',**arrays)
        tx=np.flatnonzero(np.char.startswith(arrays['branch_names'],'transformer.'))
        write_npz(out/'electrical/2025-05-01/V40F_TRANSFORMER_COEFFICIENTS.npz',branch_names=arrays['branch_names'][tx],
            current_constant=arrays['current_constant'][:,tx],current_matrix=arrays['current_matrix'][:,:,tx],
            P_constant=arrays['flow_p_constant'][:,tx],Q_constant=arrays['flow_q_constant'][:,tx],
            P_matrix=arrays['flow_p_matrix'][:,tx,:],Q_matrix=arrays['flow_q_matrix'][:,tx,:],
            kVA_ratings=np.array([np.nan if v is None else float(v) for v in c.coefficients[0].transformer_ratings])[tx])
        write_json(out/'V40F_CORRECTED_ELECTRICAL_AUTHORITY_GATE.json',{'status':'PASS','rebuilt_day':'2025-05-01',
            'new_voltage_anchor_and_sensitivities':reference(c.electrical.voltage_path),
            'new_current_and_transformer_sensitivities':reference(c.electrical.current_path),
            'corrected_April_joint_authority':reference(target/'V40E_CORRECTED_JOINT_VOLTAGE_AUTHORITY.json'),
            'old_contaminated_cache_reuse_count':0,'corrected_April_reuse':'Byte-identical corrected measurements; same frozen source and gradient selection, independent of A0 objective',
            'source_input_SHAs':c.input_shas,'coefficient_SHAs':[x.coefficient_sha256 for x in c.coefficients],
            'FULL_MAY_AUTHORIZED':'NO'})
        c.electrical.voltage.close();c.electrical.current.close()
    print('V40F electrical authority rebuilt and sealed',flush=True)


def current_context(repo):
    with electrical_namespace() as electrical:return electrical.planning_context(Path(repo).resolve(),'2025-05-01')


def source_lineage(repo):
    repo=Path(repo).resolve();sources=list((repo/'dayahead/v40f').glob('*.py'))
    sources += [repo/x for x in ['dayahead/v40a/grid.py','dayahead/v40a/feedback.py','dayahead/v40a/invariants.py','dayahead/v40e/mapping.py','dayahead/v40e/electrical.py']]
    payload={'source_SHAs':{str(p):sha(p) for p in sorted(sources)},'config':reference(repo/REL/'V40F_NORMATIVE_CORRECTION_CONTRACT.json')}
    write_json(repo/REL/'V40F_METHOD_SOURCE_LINEAGE.json',{'method_SHA':digest(payload),**payload})
    return digest(payload)
