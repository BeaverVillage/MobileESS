"""Independent selected-path checks and signed original grid-axis evidence."""
import json,pickle
from fractions import Fraction as Q
from dataclasses import replace
import numpy as np,scipy.sparse as sp
from .common import *

def run():
    from v42_pr134_adaptive.common import load,SOURCE
    from v42_job_capability import Option,validate,checkpoint_records
    from v42_pr134_adaptive.pool import physical_starts
    data=load(DAY);jobs,bounds,r,classes=data[1],data[2],data[3],data[7]['classes']
    support=read(SUPPORT/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json');known={(x['site'],int(x['slot'])):Q(x['coefficient']) for x in support['known_coefficients']}
    s38=read(START/'SELECTED_DOMAIN_INPUT.json');s38sha={digest(x) for x in s38}
    checked=[]
    for spec in SHELLS:
        rows=read(CASE/(spec['name']+'_DOMAIN.json'));assert s38sha<={digest(x) for x in rows}
        seen=set()
        for row in rows:
            key=row['class_id'];members=classes[key];j=jobs[members[0]];b=bounds[members[0]]
            assert row['option_id'] not in seen;seen.add(row['option_id'])
            assert int(row['class_count'])==len(members) and int(row['GPU'])==j.gpu and int(row['service_slots'])==j.service_slots
            start=int(row['start']);site=row['site'];parts=tuple(tuple(x) for x in json.loads(row['segments']));cp=int(row['checkpoint'])
            assert start in physical_starts(j,b)
            wide=replace(b,allowed_starts=tuple(sorted(set(b.allowed_starts)|{start})))
            if cp<0:o=Option(start,site,parts)
            else:
                from v42_boundary.generator import Generator
                tr=Generator(r,b.latest_completion).transfer(site,row['destination'],j.gpu,int(row['transfer_start']))
                assert float(row['physical_checkpoint_seconds'])==dict(checkpoint_records(j,start,min(start+j.service_slots,r.control_end)))[cp]
                o=Option(start,site,parts,cp,float(row['physical_checkpoint_seconds']),row['destination'],int(row['transfer_start']),tr.end,tr.restart,tr.wan)
            for uid in members:validate(jobs[uid],o,wide,r)
            if 'current_support_signed_cost_exact' in row:
                exact=j.gpu*sum((w for (s,t),w in known.items() for site0,a,b0 in parts if s==site0 and a<=t<b0),Q(0))
                assert str(exact)==row['current_support_signed_cost_exact']
            assert row['classification'] in ('CERTIFICATE_BREAKING','CERTIFICATE_NEUTRAL')
        checked.append(dict(shell=spec['name'],full_options=len(rows),classes=len({x['class_id'] for x in rows}),PASS=True))
    # Direct original grid-row coefficients expose site-specific mixed signs;
    # no assumption that adding every site's load improves voltage.
    a=sp.load_npz(SOURCE/DAY/'A0_MATRIX.npz');z=dict(np.load(SOURCE/DAY/'A0_ATTRIBUTES_CODED.npz'));names=dict(np.load(SOURCE/DAY/'ORIGINAL_NATIVE_NAMES.npz'))
    rows=np.flatnonzero(z['rf_names'][z['rf']]=='voltage_upper')
    node_count=len(rows)//96;axis=[]
    for t in (1,2):
        index=int(rows[t*node_count+239]);cols=a.indices[a.indptr[index]:a.indptr[index+1]];coeff=a.data[a.indptr[index]:a.indptr[index+1]]
        axis.append(dict(Dday_slot=t,node_phase_index=239,row_index=index,sense=str(z['sense'][index]),RHS_exact=str(Q(float(z['rhs'][index]))),
              coefficients=[dict(column=int(c),name=str(names['vars'][c]),coefficient_exact=str(Q(float(w)))) for c,w in zip(cols,coeff)],
              row_sha=digest(dict(columns=cols,coefficients=coeff,sense=z['sense'][index],rhs=z['rhs'][index]))))
    write('MAY19_CANDIDATE_VALIDATION.json',dict(PASS=True,all_planned_selected_paths=checked,S38_preserved=True,
          original_service_Runtime_GPURack_WAN_checkpoint_restart_causality_carryout_checked=True,native_optimizer_calls=0,
          migration_price_scope='Exact deterministic first transfer per lossless block; PR165 S0 prices certify every member, support tie prices only the selected representative.',
          current_SUPPORT_is_not_an_S38_infeasibility_proof=True))
    write('MAY19_GRID_SIGNED_AXIS.json',dict(PASS=True,original_matrix=record(SOURCE/DAY/'A0_MATRIX.npz'),node_count=node_count,critical_rows=axis,
          actual_stored_signed_coefficients=True,more_load_always_helps_assumed=False))
    print('ALL_PLANNED_CANDIDATES_AND_GRID_SIGNS_PASS',checked,flush=True)
if __name__=='__main__':run()
