from common8500 import *
from grid8500 import prepare
if __name__=='__main__':
    state(status='PREPARING',stage='VERIFY_FROZEN_AUTHORITIES',search_started=False)
    verify();ctx=new_context();state(stage='CERTIFY_FULL_ELECTRICAL_MODEL_EQUIVALENCE')
    report=prepare(ctx,P/'B1_electrical_rows')
    b0=exact(ctx.power['pcc'],(),P/'B0/exact')
    expected=read(PREF/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json')['B0_metrics']
    assert b0['status']=='PASS' and max(abs(b0['metrics'][k]-v) for k,v in expected.items())<=1e-10
    save(P/'B0/FINAL.json',dict(status='PASS',jobs=ctx.reference,metrics=b0['metrics'],MESS='OFF'))
    np.savez_compressed(P/'B0/POWER.npz',**ctx.power)
    save(P/'LAUNCH_INPUTS.json',dict(status='PASS',inputs=ctx.input_sources,preflight=record(PREF/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json'),electrical_presolve=report,B0_exact=record(P/'B0/exact/AC_VALIDATION.json')))
    state(status='READY_FOR_PRODUCTION',stage='B0_PASS',B0=b0['metrics']);print('LAUNCH_INPUTS_PASS',report,flush=True)
