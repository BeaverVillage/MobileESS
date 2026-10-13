"""Read-only controlled current-grid-block proof-chain reproduction."""
from pathlib import Path
import sys,json,hashlib
from copy import deepcopy

root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root),str(root/'tests')]
from test_v42_experimental_control import research_provider,participant,policy,metadata
from v42_integration.policy import ReservationLedger

provider=research_provider();job,receipt=participant(provider);p=policy(provider,algorithm='FIXED')
m=metadata(provider,job,receipt,sites=('A',));m['Can_Preplace']=False
ledger=ReservationLedger({'A':8,'B':8})
# Literal named synthetic source has hard current-line violations for five
# consecutive clocks. No future arrivals, actual completion, or private truth.
for t in range(5):
    p.packet.bias[t][0]+=1.
    p.packet.coefficients[t].current_constant[0]+=1.
rows=[]
for now in range(0,4501,900):
    p.set_observed_context(now=now,observed_gpu={'A':0,'B':0},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    selected=p.select(m,receipt,now,ledger,reserve=False)
    rows.append(dict(now=now,action=selected['action'],status=selected['status'],
        reference=deepcopy(p.references[job.uid]),block_proof=deepcopy(p.observed_blocks.get(job.uid)),
        selected_window=selected.get('execution_window_receipt'),
        current_grid_block=bool(p.packet._at_slot(now//900,
            -p.packet.known_gpu[now//900]-p.frozen_anonymous[now//900])[1])))
reproduced=(rows[0]['block_proof'] is not None and rows[1]['reference']['reference_start_seconds']==900
    and rows[1]['block_proof'] is None and rows[-1]['action']=='QUEUE'
    and rows[-1]['status']=='EMPTY_EXPERIMENTAL_EXECUTION_WINDOW')
files=[]
for relative in ('v42_integration/experimental_policy.py','v42_integration/experimental_actual.py',
                 'audit/independent_review/chained_reference_repro.py'):
    path=root/relative
    files.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
out=dict(schema='C_CONSECUTIVE_OBSERVED_GRID_BLOCK_R0_CHAIN_REPRO_V1',reproduced=reproduced,
    corrected_chain_PASS=(rows[-1]['action']=='START' and rows[-1]['reference']['reference_start_seconds']==4500
        and receipt.budget_seconds==1800 and m['additional_start_delay_seconds']==0),
    scope='DECLARED_SYNTHETIC_CURRENT_GRID_GEOMETRY;NOT_MAY_ACTUAL_RUN',
    finding='Advance to grid-blind R0==now drops current due-block proof; consecutive physical block chain expires',
    rows=rows,immutable_B=receipt.budget_seconds,consumed_intentional_delay=m['additional_start_delay_seconds'],
    reference_audit=p.reference_audit,source_files=files,production_source_edits=0,
    Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_calls=0)
target=root/'audit/independent_review'/('CHAINED_CURRENT_GRID_REFERENCE_REPRO_AFTER.json'
    if len(sys.argv)>1 and sys.argv[1]=='after' else 'CHAINED_CURRENT_GRID_REFERENCE_REPRO.json')
target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(reproduced=reproduced,rows=[{k:r[k] for k in ('now','action','status','current_grid_block')}|{
    'R0':r['reference']['reference_start_seconds'],'block_proof':bool(r['block_proof'])} for r in rows],output=str(target))))
