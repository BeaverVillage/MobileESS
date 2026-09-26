"""Original V41R4 physics ranking, with IEEE8500 electrical input ports only."""
from common8500 import *
import inspect,textwrap
from dayahead.v41 import physics_ranking as ranking
from frozen_binding import option_reader
from numerical_coefficients import BRANCHES,raw
from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading
from dayahead.v40a.grid import controls_from_trajectory
ORIGINAL_INIT=ranking.Ranking.__init__

def electrical_inputs(obj,ctx,power):
    line=np.arange(NL)
    names=[r.split('::')[0] for r in BRANCHES[:NL]]
    phases=[r.split('::')[1] for r in BRANCHES[:NL]]
    obj.line=names;obj.phase=phases;obj.S=np.empty((96,NL,12));rho=np.empty((96,NL))
    fixed=getattr(ctx,'v41_fixed_mess',())
    control=controls_from_trajectory(ctx.coefficients,power['pcc'],fixed)
    for t,c in enumerate(ctx.coefficients):
        x=control[t].copy();base=anchored_polygon_loading(c,x)
        rho[t]=base[:NL] if fixed else np.abs(raw(t)['line'])
        for i in range(12):
            y=x.copy();y[i]+=1e-3
            obj.S[t,:,i]=(anchored_polygon_loading(c,y)[:NL]-base[:NL])/1e-3
    return line,rho

def prepare(ctx,folder):
    folder.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter();source=textwrap.dedent(inspect.getsource(ORIGINAL_INIT))
    begin=source.index('    b0=read(');end=source.index('    order=sorted(',begin)
    adapted=source[:begin]+'    line,rho=electrical_inputs(self,ctx,power)\n'+source[end:]
    ns=dict(ORIGINAL_INIT.__globals__,electrical_inputs=electrical_inputs)
    exec(compile(adapted,__file__+'::IEEE8500_electrical_input_port','exec'),ns)
    ranking.options=option_reader(ctx);ranking.OUT=folder;ranking.INSTANCE=None
    ranking.Ranking.__init__=ns['__init__']
    try:ranking.INSTANCE=ranking.Ranking(ctx,ctx.reference,ctx.power)
    finally:ranking.Ranking.__init__=ORIGINAL_INIT
    obj=ranking.INSTANCE
    assert obj.count==7563689 and obj.temporal_candidates==181464
    assert obj.domain_digest.hexdigest()==EXPECTED
    assert all(obj.data[u]['opts']==ctx.options[u] for u in ctx.options)
    ranked,info=obj.tier(sorted(obj.jobs))
    np.savez_compressed(folder/'IEEE8500_RANKING_PHYSICS.npz',S=obj.S,B0_envelope=obj.env,weights=obj.weight,active_S=obj.AS,active_rho=obj.Arho)
    save(folder/'RANKING_INPUT_PORT_AUDIT.json',dict(status='PASS',source=record(ranking.__file__),source_constructor=source,adapted_constructor=adapted,classification='AUTHORIZED_ELECTRICAL_DIFFERENCE',candidate_stream_SHA=obj.domain_digest.hexdigest(),candidate_count=obj.count,restored_temporal_candidates=obj.temporal_candidates,original_ranking_methods_unchanged=True,original_K=ranking.K,original_M=ranking.M,coefficient_source=str(PREF/'coefficients'),previous_IEEE123_electrical_artifacts_read=False,critical=dict(line=obj.line[obj.jstar],phase=obj.phase[obj.jstar],slot=int(obj.tstar)),fixed_MESS=bool(getattr(ctx,'v41_fixed_mess',())),wall_seconds=time.perf_counter()-started,initial_tier_size=info['tier_size']))
    print('IEEE8500_ORIGINAL_PHYSICS_RANKING_PASS',time.perf_counter()-started,flush=True)
