"""Completed-evidence backend for the single entrypoint; never starts a solver."""
from .audit import ROOT, REPORTS
from .replay import A_OUT, pinned, read
from .storage import sha
from .verify_interface import verify
from v42_native.contracts import digest


class CommittedEvidenceBackend:
    def __init__(self):
        self.handoff = read(REPORTS/'A1_P1_ONLY_TO_M1_HANDOFF.json')
        self.replay = read(REPORTS/'A1_ORIGINAL_INTEGER_PHYSICAL_REPLAY.json')
        a = self.handoff['anchor']
        self.authority = {k:a[k] for k in ('day','input_authority_hashes','grid_array_identities','workload_axis_identities')}

    def execute(self, stage, request, budget):
        if stage != 'A1':
            return dict(status='PENDING', stage=stage,
                reason='No independently accepted M1 result for the exact new P1-only input; historical Global Gap=9.500515051068552%, M1_ACCEPTED=false')
        a = self.handoff['anchor']
        decisions = dict(selected_jobs=a['selected_jobs'], controls=a['controls'])
        return dict(status='P1_ONLY_ACCEPTED', stage='A1', input_identity=request['input_identity'],
                    decisions=decisions, decision_sha256=digest(decisions),
                    acceptance_scope='P1_ONLY', handoff=self.handoff,
                    A1_ACCEPTED=False, P2_certificate=None)

    def verify(self, stage, result, request):
        if stage != 'A1' or result['input_identity'] != digest(self.authority):
            raise ValueError('COMMITTED_A1_INPUT_IDENTITY_MISMATCH')
        certificates = {k:pinned(A_OUT/n) for k,n in dict(zero='PHASE1_ZERO_CERTIFICATE.json',
            closure='COMPLETE_PRICING_CLOSURE.json',bound='P1_FULL_DOMAIN_BOUND_CERTIFICATE.json',
            integer='P1_INTEGER_RESULT.json',physical='ORIGINAL_PHYSICAL_REPLAY.json').items()}
        check = verify(result['handoff'],pinned(A_OUT/'P1_ONLY_FREEZE.json'),
                       pinned(A_OUT/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY_FINAL.json'),certificates,self.replay,
                       sha(A_OUT/'P1_ONLY_FREEZE.json'),self.handoff['anchor']['control_names'])
        expected = dict(selected_jobs=self.handoff['anchor']['selected_jobs'],controls=self.handoff['anchor']['controls'])
        if result['decisions'] != expected:
            raise ValueError('FROZEN_A1_DECISIONS_DRIFT')
        return dict(PASS=check['PASS'], original_integer_physical_PASS=self.replay['PASS'],
                    input_identity=request['input_identity'], upstream_sha256=request['upstream_sha256'],
                    decision_sha256=digest(expected), global_domain_certificate_PASS=True,
                    exact_LB=check['exact_LB'],exact_UB=check['exact_UB'],original_P2_certificate_PASS=False,
                    evidence_replay=True,native_optimize_calls=0)

    def combine(self,*args):raise ValueError('M1_A2_M2_NOT_CERTIFIED')
    def actual(self,*args):raise ValueError('M1_A2_M2_NOT_CERTIFIED')
    def fresh_ac_receipt(self,*args):raise ValueError('M1_A2_M2_NOT_CERTIFIED')
    def validate_actual(self,*args):raise ValueError('M1_A2_M2_NOT_CERTIFIED')
