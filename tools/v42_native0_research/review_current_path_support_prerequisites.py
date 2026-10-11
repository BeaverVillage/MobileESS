"""Current packet algebra review only: no matrix loads or candidate generation."""
from collections import defaultdict
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
import hashlib,json

DIR=Path(r'D:\v42_multitime_audit_20261011')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def rec(p):return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)
checks=[]
def check(name,value):
    assert value,name
    checks.append(dict(name=name,PASS=True))
def f(item):return F(item['exact'])

packet_path=DIR/'CURRENT_THERMAL_LINE_WINDOW_STATIC_AUDIT.json';v=read(packet_path)
hist_path=DIR/'SOURCE19_MULTITIME_HISTORY_RECEIPT.json';hist=read(hist_path)
generic_path=DIR/'GENERIC_EXACT_PATH_SUPPORT_INDEPENDENT_REVIEW.json';generic=read(generic_path)
n0path=Path(r'D:\v42_dense_response_development_repair_20261011\NATIVE0_VALIDATION.json');n0=read(n0path)
check('required primary history audit completed first',hist['PASS'] and set(hist['required_PRs'])=={109,110,111,137,167,169,182,185,186,187})
check('generic exact all-horizon proof and small fixture PASS',generic['PASS'] and generic['general_theorem']['valid_for_all_horizons_including96'] and generic['Native_calls']==0)
check('current exact selection PASS and same current source/case authority',v['PASS'] and v['current_validation_source_SHA']==n0['source_SHA'] and v['current_case_SHA']==n0['case_SHA'])
check('one current branch and one window only',v['selection']['branch_index']==3 and v['selection']['branch_name']=='line.sw1::A' and v['window_slots']==list(range(72,80)) and len(v['exact_selected_traces'])==8)
check('no current completed LP point or claimed LB gain',v['current_verified_LP_point_available'] is False and v['LB_improvement_proven'] is False)
check('no model/native/candidate adoption',v['Native_optimize_calls']==v['Gurobi_presolve_calls']==v['model_builds']==v['candidate_generation_or_adoption']==0)
bridge=n0['physical']['original_matrix_bridge'];c=F(bridge['exact_stored_charge_coefficient']);d=F(bridge['exact_stored_discharge_coefficient'])
check('actual original all96 energy and flow bridge already independently verified',bridge['PASS'] and bridge['actual_original_energy_rows_checked']==384 and bridge['actual_original_flow_rows_checked']==9216 and bridge['actual_departure_energy_debit_verified'])
check('exact stored discharge coefficient dominates charge coefficient',d>=c>=0 and c==F(4278419646001971,18014398509481984) and d==F(4740631186705785,18014398509481984))
for row in v['actual_SOC_energy_row_support']:
    check('selected actual SOC coefficients '+str(row['row']),len(row['distinct_stored_Pch_coefficients'])==len(row['distinct_stored_Pdis_coefficients'])==1 and f(row['distinct_stored_Pch_coefficients'][0])==-c and f(row['distinct_stored_Pdis_coefficients'][0])==d)
check('all four actual initial/terminal rows present',len(v['actual_initial_and_terminal_SOC_rows'])==8)
for row in v['actual_initial_and_terminal_SOC_rows']:
    check('actual endpoint exact760 '+str(row['row']),row['sense']=='=' and f(row['rhs'])==760 and row['NNZ']==1 and len(row['terms'])==1 and f(next(iter(row['terms'].values())))==1)
check('any terminal site and original SOC return contract preserved',v['original_DAG_contract']['return_to_initial_site_required'] is False and v['original_DAG_contract']['terminal_SOC_equals_initial'] is True and bridge['terminal_site_contract']=='ANY_SITE_AT_H')
checks_net=0
for trace in v['exact_selected_traces']:
    row=trace['actual_thermal_row'];terms={n:f(x) for n,x in row['terms'].items()};weights={n:w for n,w in terms.items() if n!='rho_max'}
    check('thermal face rho sense authority slot'+str(trace['slot']),row['sense']=='<' and terms['rho_max']==-1 and len(weights) in (2,3))
    inj=defaultdict(F);const=-f(row['rhs'])
    for binding in trace['response_bindings']:
        bt={n:f(x) for n,x in binding['terms'].items()};pivots=[n for n in bt if n.startswith('response_')]
        check('response exact unit definition '+str(binding['row']),binding['sense']=='=' and len(pivots)==1 and bt[pivots[0]]==1)
        name=pivots[0];w=weights.get(name,F(0));const+=w*f(binding['rhs'])
        for n,a in bt.items():
            if n!=name:inj[n]-=w*a
    check('current stored response folding exact slot'+str(trace['slot']),dict(inj)=={n:f(x) for n,x in trace['exact_injection_coefficients'].items()} and const==f(trace['fixed_only_affine_constant']))
    raw={n:f(x) for n,x in trace['exact_raw_Pch_Pdis_Q_coefficients'].items()}
    for name,a in raw.items():
        family,suffix=name.split('[',1);unit,site,t=suffix[:-1].split(',')
        check('exact raw injection projection '+name,int(t)==trace['slot'] and a==inj[('injection_Q' if family=='Q' else 'injection_P')+'['+site+','+t+']']*(-1 if family=='Pch' else 1))
        if family=='Pch':
            check('exact cancelling charge/discharge relief direction '+name,raw['Pdis['+suffix]==-a);checks_net+=1
    check('all original nonzero raw terms retained slot'+str(trace['slot']),len(raw)==trace['projected_raw_NNZ']==288 and trace['projected_expression_uses_only_current_slot'])
pcs=v['exact_stored_PCS16_fixture'];check('actual stored PCS16 all faces preserved',len(pcs['rows'])==16 and pcs['all_16_faces_and_tiny_nonzero_stored_coefficients_preserved'])
for row in pcs['rows']:
    terms={n:f(x) for n,x in row['terms'].items()};C=terms.get(f"Pch[{pcs['mess']},{pcs['site']},{pcs['slot']}]",F(0));D=terms.get(f"Pdis[{pcs['mess']},{pcs['site']},{pcs['slot']}]",F(0))
    arcs=[(n,w) for n,w in terms.items() if n.startswith('arc[')]
    check('actual PCS net-P homogeneity row'+str(row['row']),row['sense']=='<' and f(row['rhs'])==0 and C==-D and len(arcs)==1 and arcs[0][1]<0 and all(n.startswith(('arc[','Pch[','Pdis[','Q[')) for n in terms))
receipt=dict(schema='CURRENT_ONE_WINDOW_ENERGY_PRICE_PATH_SUPPORT_INDEPENDENT_REVIEW_V1',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),checks=checks,history=rec(hist_path),current_packet=rec(packet_path),generic_theorem_and_fixture=rec(generic_path),current_Native0_authority=rec(n0path),source_SHA=n0['source_SHA'],case_SHA=n0['case_SHA'],selection=v['selection'],exact_stored_charge_coefficient=str(c),exact_stored_discharge_coefficient=str(d),exact_net_P_pairs_checked=checks_net,
    candidate='One nonnegative exact energy price, one current thermal line/window; all96slot travel and rebound included',
    conclusion='MULTITIME_LB_UNPROVEN',adoption='REJECTED_AS_ALREADY_IMPLIED_BY_EXISTING_FRACTIONAL_LP',
    mathematical_statement='For every lambda>=0, let h_st=max over original per-stay net-P PCS/connected union of wP*(D-C)+wQ*Q-lambda*(d*D-c*C). Then R<=sum_m max_full96_path(sum_stay h_st -lambda*sum_travel e) +lambda*sum_m(initialSOC-terminalSOC). Current endpoint difference=0.',
    proof='Cancel common C,D to preserve netP andQ and increase priced objective by lambda*(d-c)*min(C,D). Divide remaining controls by nonnegative stayflow. Exact homogeneous PCS and connected bounds place them in an integer-mode branch; zero stayflow forces zero controls. Bound by h_st*stayflow. All fractional unit DAG flows obey path max via Bellman potentials/telescoping. Original384 SOC rows sum over all96 slots to energy=initial-terminal. Outside-window charging remains in h_st even where thermal weights are0; every actual path ends at any original permitted terminal site. Thus the candidate holds already for every original fractional LP point and cannot cut it.',
    independent_current_source_prerequisite_scope='Selected stored thermal/PCS/energy packet algebra independently replayed; complete graph/control bridge inherits SHA-bound fresh Native0 current-source proof. No new full original matrix rebuilt or reloaded.',
    numerical_support_value_generated=False,full96_DP_run=False,new_rows=0,new_columns=0,new_binary=0,new_NNZ=0,current_LP_violation='NO_COMPLETED_CURRENT_LP_POINT_AND_THEOREM_IMPLIES_NONE_FOR_THIS_CANDIDATE',new_LB_improvement='UNPROVEN_NO_NEW_LB',Native_calls=0,model_builds=0,source_edits=0,campaign_HOLD=True)
out=DIR/'CURRENT_PATH_SUPPORT_INDEPENDENT_REVIEW.json';out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,checks=len(checks),exact_net_P_pairs_checked=checks_net,conclusion=receipt['conclusion'],adoption=receipt['adoption'],receipt=str(out),sha256=sha(out))))
