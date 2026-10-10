"""Evidence summaries; unavailable metrics stay null, never inferred PASS."""
from pathlib import Path
import itertools,csv,io,statistics
from v42_pr134_b1.common import atomic,read,record,now
from . import DAYS,ORDER

def metrics(output):
    groups={};evidence=[]
    for path in sorted(Path(output).rglob('*_PHYSICAL_AUDIT.json')):
        a=read(path)
        if 'slots_receipt' not in a:continue
        rows=read(a['slots_receipt']['path']);ns=a['namespace'];evidence.append(record(path))
        physical=[r['physical'] for r in rows]
        if not rows:continue
        g=dict(slots=len(rows),Vmin=min(p['voltage_min_pu'] for p in physical),Vmax=max(p['voltage_max_pu'] for p in physical),
            voltage_violations=sum(p['voltage_violation_cells'] for p in physical),line_current_violations=sum(p['line_current_violation_cells'] for p in physical),
            transformer_current_violations=sum(p['transformer_current_violation_cells'] for p in physical),
            transformer_nameplate_current_violations=sum(p['transformer_nameplate_current_violation_cells'] for p in physical),
            transformer_kVA_violations=sum(p['transformer_kva_violation_cells'] for p in physical),
            maximum_line_loading=max((c['loading_pu'] for p in physical for c in p['currents'] if c['element'].startswith('line.')),default=None),
            losses_kWh=sum(p['losses_W_var'][0]*.25/1000 for p in physical),losses_kvarh=sum(p['losses_W_var'][1]*.25/1000 for p in physical),
            AC_converged=all(r['settled_original_controls']['solution_converged'] for r in rows),
            control_complete=all(r['control_actions_done_as_of_current_time'] for r in rows),Full_AC_Physical_PASS=a['Full_AC_Physical_PASS'],
            SVR11_finite_rating_and_taps=all(r['svr']['hardware_PASS'] for r in rows),
            original_RegControl_count=7,SVR_bank_count=11,phase_tap_operation_evidence=a['slots_receipt'])
        taps={}
        for r in rows:
            for device in r['svr']['devices']:
                for p in device['phases']:taps.setdefault(device['id']+'::'+str(p['phase']),[]).append(p['tap'])
        g['SVR_tap_ranges']={k:dict(min=min(v),max=max(v),changes=sum(x!=y for x,y in zip(v,v[1:]))) for k,v in taps.items()}
        original={}
        for r in rows:
            for p in r['settled_original_controls']['original_regulators']:
                original.setdefault(p['name'],[]).append(p['initial_tap'])
        g['original_RegControl_tap_ranges']={k:dict(min=min(v),max=max(v),changes=sum(x!=y for x,y in zip(v,v[1:]))) for k,v in original.items()}
        g['BUS86_BUS62_original_control_interaction']={cid:[dict(original_control=k,
            simultaneous_boundary_changes=sum(any(taps[cid+'::'+str(phase)][i]!=taps[cid+'::'+str(phase)][i-1] for phase in (1,2,3)) and v[i]!=v[i-1] for i in range(1,len(v)))) for k,v in original.items()] for cid in ('BUS86','BUS62')}
        serial=[]
        for phase in (1,2,3):
            x=taps['BUS82::'+str(phase)];y=taps['BUS83::'+str(phase)]
            simultaneous=sum(a!=b and c!=d for a,b,c,d in zip(x,x[1:],y,y[1:]))
            opposite=sum((b-a)*(d-c)<0 for a,b,c,d in zip(x,x[1:],y,y[1:]))
            serial.append(dict(phase=phase,simultaneous_boundary_tap_changes=simultaneous,opposite_boundary_tap_changes=opposite))
        g['BUS82_BUS83_serial_interaction']=dict(observations=serial,interpretation='Observed boundary tap co-movement only; event receipts retain subslot actions. Causal absence of interference is not certified.')
        groups[ns]=g
    return dict(environments=groups,evidence=evidence)

def generate(root,ledger):
    root=Path(root);m=read(root/'CAMPAIGN_MANIFEST.json');rows=list(ledger['dates'].values());terminal=[r for r in rows if r['status'] in ('PASS','FAIL')]
    policies=[]
    for arm in ORDER:
        axis=[r for r in rows if r['arm']==arm];good=[r for r in axis if r['status']=='PASS']
        values=[r.get('metrics',{}).get('environments',{}).get('ACTUAL',{}).get('maximum_line_loading') for r in good];values=[v for v in values if v is not None]
        policies.append(dict(policy=arm,PASS=len(good),FAIL=sum(r['status']=='FAIL' for r in axis),RUNNING=sum(r['status']=='RUNNING' for r in axis),
            NOT_EXECUTED=sum(r['status']=='NOT_EXECUTED' for r in axis),performance_population='PASS dates for this policy only',
            mean_Actual_maximum_line_loading=statistics.mean(values) if values else None))
    paired=[]
    for a,b in itertools.combinations(ORDER,2):
        common=[day for day in DAYS if ledger['dates'][a+'/'+day]['status']==ledger['dates'][b+'/'+day]['status']=='PASS']
        paired.append(dict(policies=[a,b],same_PASS_dates=common,n=len(common)))
    document=dict(schema='V42_SVR11_CAMPAIGN_REPORT_V1',status='COMPLETE' if len(terminal)==124 else 'IN_PROGRESS',
        completed=len(terminal),total=124,source_SHA=m['execution_SHA'],hardware=m['hardware'],scenario=m['scenario'],
        policies=policies,paired_comparison_populations=paired,retrospective_design=True,independent_holdout_claim=False,
        old_SVR7_May03_FAIL_unchanged=True,monthly_zero_violation_assumed=False,dates=rows,UTC=now())
    atomic(root/'REPORT.json',document)
    lines=['# SVR11 May 2025 campaign',f"Status: {document['status']}; attempted terminal dates {len(terminal)}/124.",f"Source SHA: `{m['execution_SHA']}`",f"Hardware equipment SHA: `{read(m['hardware']['path'])['equipment_SHA']}`",'',
        'May03-informed retrospective design. May 2025 is not an independent holdout. Original SVR7 evidence and PR #206 are preserved.',
        'Date failures do not gate later dates or policies. Unexecuted metrics remain unavailable.', '', '| Policy | PASS | FAIL | RUNNING | NOT_EXECUTED |','|---|---:|---:|---:|---:|']
    lines += [f"| {p['policy']} | {p['PASS']} | {p['FAIL']} | {p['RUNNING']} | {p['NOT_EXECUTED']} |" for p in policies]
    lines += ['', 'Policy performance uses each policy’s PASS dates. Pairwise performance must use the separate same-date intersection recorded in REPORT.json.',
        'Full node/phase, both-terminal current/kVA, control events/taps and loss evidence are linked per date. No violation tolerance is relaxed. Local planning secants do not certify nonlinear AC feasibility.', '', '## Failures']
    lines += [f"- {r['arm']} {r['day']}: {r.get('reason','FAIL')} (result: {r.get('result','unavailable')})" for r in rows if r['status']=='FAIL']
    if not any(r['status']=='FAIL' for r in rows):lines.append('None recorded so far; unexecuted dates are not PASS.')
    (root/'REPORT.md').write_text('\n\n'.join(lines)+'\n',encoding='utf8')
    return document
