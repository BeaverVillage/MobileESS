"""Date-independent acceptance gates. Never resumes a partial production stage."""
def decide(s0_witness=None,s0_certificate=None,pool=None,domain=None,validation=None):
    if s0_witness and s0_witness.get('PASS') is True:
        return dict(action='STOP_AT_S0',expanded_options=0,reuse_complete_result=True)
    if not s0_certificate or s0_certificate.get('PASS') is not True:
        return dict(action='FAIL_CLOSED',reason='INDEPENDENT_S0_INFEASIBILITY_NOT_PROVEN')
    if not pool or pool.get('PASS') is not True or not pool.get('exact_rational_all_option_effects'):
        return dict(action='FAIL_CLOSED',reason='PHYSICAL_OPTION_AND_EXACT_EFFECT_VERIFICATION_REQUIRED')
    if not domain or not domain.get('full_integer_feasible') or not domain.get('lex_minimum_proven'):
        return dict(action='CONTINUE_RESTRICTED_FEASIBILITY_SEARCH',normal_objectives_authorized=False)
    if not validation or validation.get('PASS') is not True:
        return dict(action='FAIL_CLOSED',reason='FULL_UNCHANGED_SCIENTIFIC_VERIFIER_REQUIRED')
    return dict(action='DOMAIN_FEASIBILITY_READY',normal_objectives_authorized=False,both_development_cases_must_pass_before_rule_freeze=True)

def verify_gates():
    assert decide(s0_witness={'PASS':True})['action']=='STOP_AT_S0'
    assert decide(s0_certificate={'PASS':False})['action']=='FAIL_CLOSED'
    assert not decide(s0_certificate={'PASS':True},pool={'PASS':True,'exact_rational_all_option_effects':True},
                      domain={'full_integer_feasible':True,'lex_minimum_proven':False})['normal_objectives_authorized']
    assert decide(s0_certificate={'PASS':True},pool={'PASS':True,'exact_rational_all_option_effects':True},
                  domain={'full_integer_feasible':True,'lex_minimum_proven':True},validation={'PASS':False})['action']=='FAIL_CLOSED'
    assert not decide(s0_certificate={'PASS':True},pool={'PASS':True,'exact_rational_all_option_effects':True},
                      domain={'full_integer_feasible':True,'lex_minimum_proven':True},validation={'PASS':True})['normal_objectives_authorized']
    return dict(PASS=True,adversarial_gate_cases=5,partial_resume_supported=False,date_specific_candidate_lists=False)

if __name__=='__main__':
    from .common import write
    write('CONTROLLER_GATE_VERIFICATION.json',verify_gates())
