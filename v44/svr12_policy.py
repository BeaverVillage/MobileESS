"""Existing V43 signed ranking; SVR12 Current AC is the physical authority.

The intentionally different Planning grid is a ranking proxy, never an Actual
voltage certificate. No historical affine/AC mismatch count is fabricated.
"""
from .common import read,record,verify,digest,DOC
from .svr12 import SVR12CurrentAC,HARDWARE,certificate
from v43_corrective.policy import CorrectivePolicy
from .daily import clone

class SVR12CorrectivePolicy(CorrectivePolicy):
    def __init__(self,*args,correction_proof=None,**kwargs):
        if correction_proof is not None:raise PermissionError('OLD_GRID_CORRECTION_PROOF_FORBIDDEN_FOR_SVR12')
        oracle=kwargs.get('oracle')
        if not isinstance(oracle,SVR12CurrentAC) or oracle.hardware_record!=record(HARDWARE/'HARDWARE.json'):
            raise PermissionError('SVR12_LIVE_CURRENT_AC_REQUIRED')
        certificate(DOC/'v43_planning_svr12_actual_v1/CURRENT_AC_CERTIFICATION.json')
        super().__init__(*args,correction_proof=None,**kwargs)
        self.affine_hard_gate=False
        self.spec.update(signed_model='UNCHANGED_V43_SIGNED_RANKING_PROXY_NOT_ACTUAL_PHYSICS',
            signed_current_hard_gate=False,final_execution_gate='SVR12_CURRENT_NATIVE_TIME_AC',
            Actual_hardware=oracle.hardware_record,intentional_two_grid_research_design=True,
            old_correction_proof_reused=False,physical_limits_unchanged=True)
        self.sha=digest(self.spec)

def corrective_driver(original_run,shared,bindings,day_start):
    from .svr11_actual import corrective_driver as original
    run=original(original_run,shared,bindings,day_start)
    class Routed(SVR12CurrentAC):
        def __init__(self,*args,**kwargs):super().__init__(*args,arm=bindings.arm,**kwargs)
    return clone(run,CorrectivePolicy=SVR12CorrectivePolicy,CertifiedPrefixAC=Routed,
        FullPrefixReferenceAC=Routed,ShadowCertifiedPrefixAC=Routed,_svr11_certificate=certificate)
