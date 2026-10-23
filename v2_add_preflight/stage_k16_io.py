"""Reuse pure K16 construction only for identical original numeric inputs.

No historical point, bound, accepted plan or Native clock is reused. Original
verify_packet rederives the current source/physical-box/exact-cut certificate.
"""
import numpy as np
import scipy.sparse as sp
from .stage_common import WORK,read,record


def prepare(module,case,output):
    folder=WORK/'M1/K16';manifest=folder/'NATIVE0_MANIFEST.json'
    source=module.identity(case)
    if not manifest.exists():return module.prepare_k16(case,None,output)
    old=read(manifest)
    if (old['source']['matrix_sha'],old['source']['domain_sha'])!=(source['matrix_sha'],source['domain_sha']):
        return module.prepare_k16(case,None,output)
    for item in old['files']:
        if record(item['path'])!=item:raise ValueError('PURE_K16_CONSTRUCTION_CACHE_BYTES_CHANGED')
    def arrays(path):
        with np.load(path) as z:return {k:z[k] for k in z.files}
    axes=arrays(folder/'JOINT_AXES.npz')
    packet=dict(A=sp.load_npz(folder/'JOINT_A.npz'),d=arrays(folder/'JOINT_DATA.npz'),
        rows=axes['rows'],columns=axes['columns'],cuts=read(folder/'EXACT_CUTS.json'),
        start=None,full_start=None,source=source,original_replay=None,K=16,
        selection=old['selection'],historical_point_or_bound_read=False,build_wall_seconds=0.)
    proof=module.verify_packet(case,packet);module.save_packet(packet,proof,output)
    from .prestart_execution import atomic
    atomic(__import__('pathlib').Path(output)/'CURRENT_NUMERIC_INPUT_CACHE_EQUIVALENCE.json',dict(PASS=True,
        cached=record(manifest),current_source=source,original_matrix_and_domain_identical=True,
        source_row_selection_inputs_bit_identical=True,all_physical_rows_bounds_and_exact_cuts_reverified=True,
        point_UB_LB_or_Native_clock_reused=False,current_proof_sha=proof['certificate_sha']))
    return packet,proof
