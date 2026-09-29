"""One bounded four-stage architecture; implementation readiness != science gate."""
from .contracts import require,digest,lex_not_worse
from .supervision import supervise
from .actual import require_fresh_ac

NATIVE_REQUIRED=('reference_resources','native_grid','runtime_where_required','CC4_where_required',
    'final_kernel_anchor','service_windows','security_margin','MESS_initial_state','traffic_routes')


def gate(receipts):
    missing=[k for k in NATIVE_REQUIRED if receipts.get(k) is not True]
    return dict(PASS=not missing,missing=missing)


def run(backend,output,*,seconds=600):
    require(0<seconds<=600,'CANARY_BLOCK_CAP')
    check=gate(backend.preflight());require(check['PASS'],'NATIVE_GATE:'+','.join(check['missing']))
    a=m=None;receipts={}
    for stage in ('A1','M1','A2','M2'):
        payload=backend.stage_payload(stage,a,m)
        # Explicit stage state handoff, not a future scientific-data cache.
        payload['warm_start']=a if stage=='A2' else m if stage=='M2' else None
        candidate,receipt=supervise(stage,backend.worker,backend.validator,payload,output/stage,seconds)
        require(candidate is not None,'NO_VALIDATED_STAGE_INCUMBENT')
        if stage=='M2':
            require(lex_not_worse(backend.objective(a,candidate),backend.objective(a,m)),'M2_FIXED_A2_NO_REGRET')
        if stage.startswith('A'):a=candidate
        else:m=candidate
        receipts[stage]=receipt
    final=backend.combine(a,m)
    ac=backend.fresh_ac(final)
    require_fresh_ac(ac,digest(final),backend.grid_sha)
    return dict(final=final,stages=receipts,fresh_ac=ac)
