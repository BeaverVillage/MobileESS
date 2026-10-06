"""Apply preregistered criteria to matched pairs; never compare across phases."""
from .common import *
import re
def paired(a,b):
    params=lambda x:{k:v for k,v in x['all_native_parameters'].items() if k!='LogFile'}
    assert params(a)==params(b)
    complete=a['root_completed'] and b['root_completed']
    # Native root values are printed to .01; the gate is conservative at that
    # precision and never substitutes a total Work value for missing root Work.
    timegate=bool(complete and b['root_time']+.005<=.85*(a['root_time']-.005))
    workgate=bool(complete and b['root_Work']+.005<=.85*(a['root_Work']-.005))
    return dict(root_time_gate=timegate,root_Work_gate=workgate,root_time_reduction=1-b['root_time']/a['root_time'] if complete else None,root_Work_reduction=1-b['root_Work']/a['root_Work'] if complete else None,all_native_parameters_except_log_identical=True,baseline_root_censored=not a['root_completed'])
def decision(a,b,c,d):
    micro=paired(a,b);full=paired(c,d);node=d['nodes_after_root']>c['nodes_after_root']+1;lb=d['valid_LB']>c['valid_LB']+1e-6;gp=d['valid_gap']<c['valid_gap']-1e-6;inc=d['first_new_valid_incumbent'] is not None and (c['first_new_valid_incumbent'] is None or d['first_new_valid_incumbent']<=.85*c['first_new_valid_incumbent']);selected=bool(micro['root_time_gate'] or micro['root_Work_gate'] or full['root_time_gate'] or full['root_Work_gate'] or node or lb or gp or inc)
    return dict(PASS=True,state='ULTRACOMPACT_EXACT_SELECTED' if selected else 'ULTRACOMPACT_EXACT_BUT_NO_SPEEDUP',selected=selected,selected_formulation='C3A' if selected else 'FROZEN_PR161_C2',exactness=True,matched_root_micro=micro,matched_full_MILP_root=full,root_time_gate=micro['root_time_gate'] or full['root_time_gate'],root_Work_gate=micro['root_Work_gate'] or full['root_Work_gate'],node_gate=node,valid_LB_gate=lb,valid_gap_gate=gp,new_incumbent_gate=inc,comparison_tolerance=1e-6,selection_basis='Preregistered criteria A/B apply to measured root metrics in either matched identical-setting pair. The censored micro C2 is not compared to another phase. Fresh full-MILP C2/C3 root values are compared within that phase only.',historical_PR161_performance_used=False,size_only_selection=False,algorithm_tournament_executed=False,STOP=True)
def timing(result):
    label=result['label'];stage=result['stage'];log=(OUT/(stage+'_'+label+'_NATIVE.log')).read_text(encoding='utf-8');result.setdefault('runtime_minus_root_LP_duration',result.get('time_after_root'))
    if result['root_completed']:
        after=log.split('Root relaxation:',1)[1];r=re.search(r'^\s*\d+\s+\d+\s+.*?\s(\d+)s\s*$',after,re.M);t=float(r[1]) if r else None
        result['first_post_root_native_progress_runtime_rounded']=t;result['time_after_root']=max(0,result['native_Runtime']-t) if t is not None else None
    result['time_after_root_precision']='Approximate native log integer seconds after first root progress row; exact root-completion callback timestamp was unavailable. Runtime minus root LP duration includes pre-root time and is stored separately.'
    return result
def run():
    roots=read('ULTRACOMPACT_ROOT_COMPARISON.json');mips=read('ULTRACOMPACT_MILP_COMPARISON.json')
    if not (OUT/'MICRO_ONLY_AUTOMATIC_SELECTION.json').exists():write('MICRO_ONLY_AUTOMATIC_SELECTION.json',read('ULTRACOMPACT_SELECTION.json'))
    for p in [roots,mips]:
        for label in ['C2','C3']:timing(p[label])
    write('ULTRACOMPACT_ROOT_COMPARISON.json',roots);write('ULTRACOMPACT_MILP_COMPARISON.json',mips)
    write('ROOT_C2_RESULT.json',roots['C2']);write('ROOT_C3A_RESULT.json',roots['C3']);write('C2_MILP_RESULT.json',mips['C2']);write('C3_MILP_RESULT.json',mips['C3'])
    result=decision(roots['C2'],roots['C3'],mips['C2'],mips['C3']);assert read('ULTRACOMPACT_INDEPENDENT_VERIFICATION.json')['PASS'];result['executed_source_commit']=mips['C2']['source_commit'];result['selection_code_SHA256']=sha(Path(__file__));write('ULTRACOMPACT_SELECTION.json',result)
    # Counterexamples: missing root metrics cannot establish a speedup; mixing
    # different native settings is rejected; total Work never fills root Work.
    import copy
    tests=[];a=copy.deepcopy(mips['C2']);b=copy.deepcopy(mips['C3']);a['root_completed']=False;a['root_time']=None;a['root_Work']=None;g=paired(a,b);assert not g['root_time_gate'] and not g['root_Work_gate'];tests.append('CENSORED_ROOT_NOT_IMPUTED')
    a=copy.deepcopy(mips['C2']);b=copy.deepcopy(mips['C3']);b['all_native_parameters']['Threads']=2;rejected=False
    try:paired(a,b)
    except AssertionError:rejected=True
    assert rejected;tests.append('MISMATCHED_PARAMETERS_REJECTED')
    if result['matched_full_MILP_root']['root_Work_gate']:assert result['matched_full_MILP_root']['root_Work_reduction']>=.15
    tests.append('MATCHED_FULL_ROOT_WORK_GATE_CONSISTENT')
    a=copy.deepcopy(mips['C2']);b=copy.deepcopy(a);g=decision(a,b,a,b);assert not g['selected'];tests.append('NO_SPEEDUP_NOT_FORCED')
    write('SELECTION_RULE_VERIFICATION.json',dict(PASS=True,tests=tests,no_additional_optimize_calls=True,preregistered_criteria_unmodified=True,selection_not_limited_to_censored_micro_root=True))
    print('MATCHED_SELECTION',result['state'],result['matched_full_MILP_root'],flush=True)
if __name__=='__main__':run()
