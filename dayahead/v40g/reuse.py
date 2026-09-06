"""B3 A0 is an immutable B1 artifact handle, never an optimization stage."""
from dataclasses import dataclass
from pathlib import Path
import shutil
import numpy as np
from dayahead.paper_analysis.storage import read,write_json,reference,sha
from dayahead.v40a.invariants import digest

ROLE='REUSED_ACCEPTED_B1_AIDC_STATE_NOT_NEW_OPTIMIZATION'


@dataclass(frozen=True)
class B1AsA0:
    accepted_b1_path: Path
    b1_trajectory_path: Path
    b1_file_sha: str
    trajectory_file_sha: str
    decision_sha: str

    def verify(self):
        if sha(self.accepted_b1_path)!=self.b1_file_sha or sha(self.b1_trajectory_path)!=self.trajectory_file_sha:
            raise ValueError('ACCEPTED_B1_SOURCE_DRIFT')
        value=read(self.accepted_b1_path)
        if value['status']!='PASS' or value.get('diagnostic_only') is not False:
            raise ValueError('FINAL_ACCEPTED_B1_REQUIRED')
        if digest(sorted(value['jobs'],key=lambda r:r['job_uid']))!=self.decision_sha or value['final_decision_SHA']!=self.decision_sha:
            raise ValueError('B1_DECISION_SHA_MISMATCH')
        with np.load(self.b1_trajectory_path) as z:
            if not np.array_equal(z['gpu'],np.asarray(value['GPU'])) or not np.array_equal(z['pcc'],np.asarray(value['PCC'])):
                raise ValueError('B1_TRAJECTORY_MISMATCH')
        return self


def accepted_b1_as_a0(accepted_b1_path, b1_trajectory_path):
    """Return the B1 source itself. No reconstruction or alternate tie-break."""
    path=Path(accepted_b1_path).resolve();trajectory=Path(b1_trajectory_path).resolve()
    value=read(path)
    return B1AsA0(path,trajectory,sha(path),sha(trajectory),value['final_decision_SHA']).verify()


def persist_reuse(handle,output):
    """Optional archival aliases are byte copies, not rematerialized decisions."""
    handle.verify();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for src,name in [(handle.accepted_b1_path,'B1_FINAL_AS_A0.json'),(handle.b1_trajectory_path,'B1_FINAL_AS_A0_TRAJECTORY.npz')]:
        dst=output/name
        if dst.exists():
            if sha(dst)!=sha(src):raise ValueError('A0_ALIAS_DRIFT')
        else:shutil.copyfile(src,dst)
        assert dst.read_bytes()==src.read_bytes()
    result={'B3_A0_ROLE':ROLE,'B3_A0_AIDC_OPTIMIZE_CALLS':0,
            'B1_FINAL_AIDC_DECISION_SHA':handle.decision_sha,'B3_A0_DECISION_SHA':handle.decision_sha,
            'B1_B3_A0_IDENTITY':'PASS','B1_B3_A0_EXACT_IDENTITY':'PASS',
            'B3_A0_GPU_TRAJECTORY_EQUALS_B1':True,'B3_A0_PCC_TRAJECTORY_EQUALS_B1':True,
            'B3_A0_START_SITE_MIGRATION_DECISIONS_EQUALS_B1':True,
            'DUPLICATE_A0_AIDC_OPTIMIZATION':'FORBIDDEN','scientific_decision_rematerialization_calls':0,
            'accepted_B1':reference(handle.accepted_b1_path),'B1_trajectory':reference(handle.b1_trajectory_path),
            'identity_scope':'STATIC_REUSE_TEST_ONLY; B3 SCIENCE NOT EXECUTED',
            'B2_B3_AUTHORIZED':'NO','FULL_MAY_AUTHORIZED':'NO'}
    write_json(output/'A0_REUSE_GATE.json',result);return result


def validate_m1_conditioning(handle, conditioning):
    """Before any future authorized M1, reject B0/B2 conditional results."""
    handle.verify()
    expected={'AIDC_decision_SHA':handle.decision_sha,'AIDC_trajectory_file_SHA':handle.trajectory_file_sha}
    if any(conditioning.get(k)!=v for k,v in expected.items()):raise ValueError('M1_MUST_BE_CONDITIONED_ON_EXACT_B1_AIDC')
    for name in ('corrected_Planning_electrical_authority_SHA','common_T_DA_SHA','causal_traffic_authority_SHA','MESS_mobility_energy_authority_SHA'):
        if not conditioning.get(name):raise ValueError('M1_MISSING_AUTHORITY:'+name)
    if conditioning.get('B2_result_accepted_without_M1_reoptimization',False):
        raise ValueError('B2_CANNOT_BYPASS_B3_M1')
    return True


def architecture_contract(repo):
    from .authority import REL,GATES
    root=Path(repo)/REL
    value={'B3_A0_ROLE':ROLE,'B3_FLOW':'B1_FINAL_AS_A0 -> M1_FULL_MESS_ROUTE_PQ -> A1_AIDC_FEEDBACK -> MF_FIXED_ROUTE_PQ_RECOURSE',
           'B1_B3_A0_EXACT_IDENTITY':'REQUIRED','DUPLICATE_A0_AIDC_OPTIMIZATION':'FORBIDDEN',
           'normative_scientific_stage_counts':{'B1_AIDC_OPTIMIZE_CALLS':1,'B3_A0_AIDC_OPTIMIZE_CALLS':0,
                 'B3_M1_ROUTE_SEARCH_CALLS':1,'B3_A1_AIDC_OPTIMIZE_CALLS':1,'B3_MF_PQ_OPTIMIZE_CALLS':1},
           'B3_FULL_MESS_ROUTE_SEARCH_COUNT':1,'B3_ROUTE_SEARCH_COUNT_TOTAL':1,
           'M1_conditioning':['exact accepted B1 GPU/PCC P/Q','corrected Planning electrical authority','common T_DA','causal traffic','MESS mobility/energy'],
           'B2_as_M1':'Only optional warm start; B3 M1 optimization against B1 remains mandatory',
           'A1':'MIN_RHO feedback against frozen M1; same service, terminal, capacity, Rack, RUNNING, WAN and causal constraints',
           'MF':'Freeze route/destination/departure/STAY_MOVE/transit/arrival/ready; authorized P/Q/energy recourse only',
           'solver_subcalls_counted_separately':True,'UNASSIGNED_44_CASE_BLOCKER':'OPEN',
           'additional_request':reference(Path('C:/Users/kjw39/.codex/attachments/2e142e4c-66bf-4701-9052-3629704aacf5/pasted-text.txt')),**GATES}
    path=root/'B1_REUSE_AS_B3_A0_CONTRACT.json'
    if path.exists():assert read(path)==value
    else:write_json(path,value)
    return value
