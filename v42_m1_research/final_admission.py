"""Immutable final-admission view of a completed run; no second Native budget."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from time import perf_counter
import numpy as np
from .case import REPORTS,load_case
from .check_ub import validate_candidate,vector_sha
from .check_joint import check_exact_integer_replay
from v42_unified.audit import ROOT,write
from v42_unified.storage import sha

REFERENCE_KEYS={'dual_evidence','raw_dual_evidence','repaired_dual_evidence','row_proof_evidence'}

def repoint_evidence(value,original,view):
    """Change operational evidence paths only; no cover, multiplier or ledger data."""
    if isinstance(value,dict):
        for key,child in value.items():
            if key in REFERENCE_KEYS and isinstance(child,dict) and 'path' in child:
                previous=Path(child['path']).resolve()
                if not previous.is_relative_to(original):raise ValueError('EVIDENCE_OUTSIDE_ORIGINAL_RUN')
                copied=view/previous.relative_to(original)
                if sha(copied)!=child['sha256']:raise ValueError('COPIED_EVIDENCE_BYTE_DRIFT')
                child['path']=str(copied)
            else:repoint_evidence(child,original,view)
    elif isinstance(value,list):
        for child in value:repoint_evidence(child,original,view)


def create_view(original,*,case=None):
    """Preserve all producer outputs, admit the separately verified Native RAW point."""
    begin=perf_counter();original=Path(original).resolve()
    base=(ROOT/'runtime/v42_m1_joint_gap_research').resolve()
    if not original.is_relative_to(base):raise ValueError('D_RESEARCH_RUN_REQUIRED')
    case=load_case() if case is None else case
    if not (original/'RESEARCH_TRACK_RESULTS.json').is_file():raise ValueError('COMPLETED_REGISTERED_RUN_REQUIRED')
    ledger=json.loads((original/'NATIVE_RUNTIME_LEDGER.json').read_text(encoding='utf8'))
    result=json.loads((original/'RESEARCH_TRACK_RESULTS.json').read_text(encoding='utf8'))
    if ledger['inflight'] is not None or result['ledger']!=ledger:raise ValueError('REGISTERED_RUN_NOT_FINALIZED')
    if result['case_sha']!=case.case_sha:raise ValueError('FINAL_ADMISSION_CASE_DRIFT')
    packet=REPORTS/'FINAL_STRICT_ADMITTED_UB_POINT.npz'
    # This packet is a byte-identical copy of the saved U2 Native final RAW.
    native_raw=REPORTS/'U2_RAW_POINT.npz'
    if sha(packet)!=sha(native_raw):raise ValueError('STRICT_POINT_IS_NOT_UNCHANGED_NATIVE_RAW')
    with np.load(packet,allow_pickle=False) as archive:
        if archive.files!=['point']:raise ValueError('STRICT_RAW_POINT_AXIS_DRIFT')
        point=archive['point'].copy()
    checked=validate_candidate(case,point)
    if not checked['PASS']:raise ValueError('STRICT_RAW_FULL_ORIGINAL_PHYSICAL_REPLAY_FAILED')
    check_exact_integer_replay(checked)
    if checked['objective']!=result['UB']['best_validated_global_UB']:raise ValueError('STRICT_RAW_RHO_NOT_REGISTERED_BEST')
    originals={p.name:sha(p) for p in original.iterdir() if p.is_file() and p.suffix in ('.npz','.json','.log')}
    view=base/(original.name+'_final_strict_admission_view')
    view.mkdir(parents=True,exist_ok=False)
    for name,digest in originals.items():
        shutil.copyfile(original/name,view/name)
        if sha(view/name)!=digest:raise ValueError('FINAL_ADMISSION_COPY_DRIFT')
    adjusted=deepcopy(result)
    repoint_evidence(adjusted,original,view)
    adjusted['run_path']=str(view)
    write(view/'RESEARCH_TRACK_RESULTS.json',adjusted)
    shutil.copyfile(packet,view/'FINAL_VALID_UB_POINT.npz')
    if any(sha(original/name)!=digest for name,digest in originals.items()):raise ValueError('ORIGINAL_REGISTERED_RUN_CHANGED')
    receipt=dict(PASS=True,schema='V42_FINAL_STRICT_ADMISSION_VIEW_V1',case_sha=case.case_sha,
        original_run=str(original),read_only_replay_view=str(view),
        original_files_SHA256=originals,original_files_unchanged=True,
        original_native_ledger_sha256=sha(original/'NATIVE_RUNTIME_LEDGER.json'),
        view_native_ledger_sha256=sha(view/'NATIVE_RUNTIME_LEDGER.json'),
        native_ledger_is_byte_identical_read_only_copy_not_new_budget=True,
        original_final_UB_checkpoint_unchanged=True,original_pool_unchanged=True,
        selected_Native_RAW_packet=dict(path=str(native_raw),sha256=sha(native_raw),vector_sha256=vector_sha(point)),
        selected_view_packet=dict(path=str(view/'FINAL_VALID_UB_POINT.npz'),sha256=sha(view/'FINAL_VALID_UB_POINT.npz')),
        same_registered_best_rho_binary64=True,strict_original_replay=checked,
        final_exact_gate_unchanged=True,additional_Native_optimize_calls=0,
        additional_Native_Runtime=0,repairs=0,rounding=0,clipping=0,
        operational_dual_evidence_path_remap_only=True,view_creation_wall_seconds=perf_counter()-begin)
    write(REPORTS/'FINAL_ADMISSION_VIEW.json',receipt)
    write(view/'READ_ONLY_FINAL_ADMISSION_VIEW.json',receipt)
    return view,receipt

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('original_run');args=parser.parse_args()
    view,receipt=create_view(args.original_run)
    print('FINAL_STRICT_ADMISSION_VIEW',str(view),receipt['PASS'])
