"""Regression gates A–P for auxiliary reconstruction, scientific identity and honest bounds."""
import inspect
import numpy as np
import pytest
import gurobipy as gp
from scipy import sparse
from v42_exact_start import common as c,reconstruct as r,engine as e
from v42_exact_start.progress import parse_lines

@pytest.fixture(scope='module')
def audited():
    result={}
    with np.load(c.ROOT/'docs/v42_m1_integrality_gap_root_cause/F3_MODEL_AXIS.npz') as z:native=z['rownames']
    with gp.Env(params={'OutputFlag':0}) as env:
        for kind in ['original','compact']:
            m=c.model(kind,env);names,old=c.old_start(kind);newnames,new=c.start(kind)
            assert np.array_equal(names,newnames)
            rows=native if kind=='original' else np.concatenate([native,np.array(['compact_added_definition']*(m.NumConstrs-len(native)))])
            rules,A,rhs,mask=r.binding_rules(m,names,rows)
            result[kind]=dict(names=names,old=old,new=new,mask=mask,before=r.matrix_audit(m,old),after=r.matrix_audit(m,new),
                              repeated=r.substitute(A,rhs,rules,old))
            m.dispose()
    return result

def test_A_saved_original_residual(audited):
    assert audited['original']['before']['maximum_row_violation']==3.0752360699604075e-8

@pytest.mark.parametrize('kind',['original','compact'])
def test_B_C_full_reconstructed_matrix(kind,audited):
    a=audited[kind]['after'];assert a['PASS'] and a['rows_exceeding_1e8']==a['rows_exceeding_1e9']==0
    assert a['maximum_row_violation']<=1e-9 and a['max_bound_violation']<=1e-10 and a['max_integer_fractionality']==0

@pytest.mark.parametrize('kind',['original','compact'])
def test_D_E_F_all_primary_bits_and_controls(kind,audited):
    a=audited[kind];assert np.array_equal(a['old'][a['mask']].view(np.uint64),a['new'][a['mask']].view(np.uint64))
    assert a['after']['objective']==c.UB

def test_G_full_bidirectional_mapping(audited):
    a=audited['original']['new'];b=audited['compact']['new']
    assert np.array_equal(sparse.load_npz(c.OLD_CACHE/'FORWARD_F.npz')@a,b)
    assert np.array_equal(sparse.load_npz(c.OLD_CACHE/'INVERSE_T.npz')@b,a)

@pytest.mark.parametrize('kind',['original','compact'])
def test_H_deterministic_values_and_serialized_SHA(kind,audited):
    assert np.array_equal(audited[kind]['new'].view(np.uint64),audited[kind]['repeated'].view(np.uint64))
    assert c.sha(c.LOCAL/(kind.upper()+'_RECONSTRUCTED_START.npz'))==c.sha(c.LOCAL/(kind.upper()+'_DETERMINISM_REPEAT.npz'))

def test_I_reconstruction_no_optimizer(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('optimizer forbidden in reconstruction')
    monkeypatch.setattr(gp.Model,'optimize',forbidden)
    A=sparse.csr_matrix([[2.,1.,0.],[0.,3.,1.]])
    assert np.array_equal(r.substitute(A,np.array([7.,11.]),[(1,0),(2,1)],np.array([2.,99.,99.])),[2.,3.,2.])
    assert '.optimize(' not in inspect.getsource(r)

def test_J_K_frozen_policy():
    assert c.SETTINGS==c.read('PREREGISTRATION.json')['solver']
    assert c.SETTINGS['FeasibilityTol']==1e-8 and c.SETTINGS['Threads']==4 and c.SETTINGS['Heuristics']==0
    for label in ['START_ACCEPTANCE_ORIGINAL','START_ACCEPTANCE_COMPACT','CANARY_ORIGINAL_600S','CANARY_COMPACT_600S']:
        receipt=c.read(label+'.json');assert all(receipt['settings'][k]==v for k,v in c.SETTINGS.items())

def test_L_inherited_certificate():
    receipt=c.read('INHERITED_CERTIFICATE_PRESERVATION.json');assert receipt['UB']==c.UB and receipt['LB']==c.LB
    assert e.interval(.28,None)['valid_retained_LB']==c.LB

def test_M_N_source_matrices_and_route_domain_preserved():
    c.solver_freeze_check();assert c.preserve()==2469
    assert c.read('PHYSICAL_IDENTITY_AUDIT.json')['route_mode_bits_unchanged']

def test_O_no_full_Benders_experiment():
    assert c.read('PREREGISTRATION.json')['Benders_calls']==0
    assert 'v42_benders' not in inspect.getsource(e)

def test_P_missing_incumbent_conservative(monkeypatch):
    writes={};monkeypatch.setattr(e,'read',lambda *a:dict(PASS=False,raw_BestBd=.28))
    monkeypatch.setattr(e,'dump',lambda n,v:writes.update({n:v}))
    result=e.compare();assert not result['PASS'] and not result['COMPACT_M1_PRODUCTION_AUTHORIZED']
    assert result['compact']['validated_retained_UB']==c.UB and result['compact']['valid_retained_LB']==c.LB

def test_log_infeasible_phase_objective_is_not_a_bound():
    result=parse_lines([' 89799 2.30e+02 1.00e+06 0.0 236s'])
    assert result[0]['simplex_phase_objective']==230 and result[0]['primal_infeasibility']==1e6
    assert 'BestBd' not in result[0] and 'Incumbent_UB' not in result[0]

def test_contradictory_bound_fails_conservatively():
    result=e.interval(c.UB+.01,None);assert not result['PASS'] and result['valid_retained_LB']==c.LB
