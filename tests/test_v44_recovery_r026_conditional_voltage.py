from fractions import Fraction as F
from types import SimpleNamespace
from dataclasses import replace
import inspect
import numpy as np
from scipy import sparse
import pytest
import v44_recovery_r026
from v44.common import atomic,read,record
from v44_recovery_r026.conditional_voltage import ConditionalVoltage,compile_conditional,LOWER_DELTA,UPPER_DELTA,validate_execution
from v44_recovery_r026.row_generation import compile_phase,ActiveRows
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_phase1.core import elastic_master
from v42_a_stage_phase1.backend import artificial_point


def fixture(tmp_path):
    snapshot=LinearSnapshot(sparse.csr_matrix((193,1)),np.zeros(1),np.ones(1),np.array(['>']*96+['<']*97),
        np.r_[np.full(96,.01),np.ones(97)],np.array(['C']),(Objective('rho',((0,F(1)),),0),)).require()
    state=dict(compact=snapshot,reference=snapshot,grows=tuple(range(193)),n=1,axes={},
        atlas=dict(node_names=['n.1'],rf=np.array([0]*96+[1]*96+[2]),rf_names=['voltage_lower','voltage_upper','GPU'],
            voltage_lower_rows=np.arange(96),voltage_upper_rows=np.arange(96,192)))
    controller=ConditionalVoltage(dict(output=str(tmp_path)))
    master=SimpleNamespace(artificial_rows=[0,192],weights=[F(1),F(1)])
    return controller,state,master


def observe(c,state,master,tmp_path,activation,voltage,other=0):
    folder=tmp_path/str(len(c.history));folder.mkdir()
    point=np.array([0.,voltage,other]);phi=F(float(voltage))+F(float(other))
    atomic(folder/'R026_FULL_PHI.json',dict(PASS=True,exact_full_Phi=str(phi)))
    return c.observe(state,master,point,phi,activation,folder)


def sweep(c,tmp_path):
    path=tmp_path/'price.json';atomic(path,dict(PASS=True,classes_priced=2,class_ids=['a','b']))
    c.full_sweeps.append(dict(PASS=True,eligible_classes=2,eligible_class_ids=['a','b'],pricing_result=record(path)))


def test_requires_full_sweep_and_two_real_activations_not_rechecks(tmp_path):
    c,s,m=fixture(tmp_path)
    assert not observe(c,s,m,tmp_path,0,100)
    assert not observe(c,s,m,tmp_path,0,99)
    assert not c.gains
    assert not observe(c,s,m,tmp_path,1,98)
    assert not observe(c,s,m,tmp_path,2,97)
    sweep(c,tmp_path)
    assert observe(c,s,m,tmp_path,2,97)
    assert len(c.gains)==2 and len(c.proposal['verified_unrelaxed_voltage_violations'])==1


@pytest.mark.parametrize('voltage,other,allowed',[(95,5,True),(94,6,False)])
def test_voltage_fraction_95_percent_is_inclusive(tmp_path,voltage,other,allowed):
    c,s,m=fixture(tmp_path);sweep(c,tmp_path)
    observe(c,s,m,tmp_path,0,voltage+2,other)
    observe(c,s,m,tmp_path,1,voltage+1,other)
    assert observe(c,s,m,tmp_path,2,voltage,other)==allowed


def test_exactly_five_percent_decrease_does_not_trigger(tmp_path):
    c,s,m=fixture(tmp_path);sweep(c,tmp_path)
    observe(c,s,m,tmp_path,0,20);observe(c,s,m,tmp_path,1,19)
    assert not observe(c,s,m,tmp_path,2,18.9)


def test_first_targeted_sweep_prices_every_eligible_class(tmp_path):
    c,s,m=fixture(tmp_path);c.attribution=dict(classes_ranked=[dict(class_id='a',inactive_candidates_available=True),
        dict(class_id='b',inactive_candidates_available=True),dict(class_id='done',inactive_candidates_available=False)])
    def targeted(*args):
        result=dict(PASS=True,class_ids=args[12],classes_priced=len(args[12]))
        atomic(args[-1]/'PRICING_RESULT.json',result);return result,[]
    folder=tmp_path/'PRICE';args=[None]*16;args[12]=['a'];args[-1]=folder
    result,_=c.wrap_targeted(targeted)(*args)
    assert result['class_ids']==['a','b'] and len(c.full_sweeps)==1


def test_apply_changes_only_verified_direction_row_and_resets_dual(tmp_path):
    c,s,m=fixture(tmp_path);sweep(c,tmp_path)
    observe(c,s,m,tmp_path,0,100);observe(c,s,m,tmp_path,1,99)
    assert observe(c,s,m,tmp_path,2,98)
    from v44_recovery_r026.a2_continue import FrozenWeights
    frozen=FrozenWeights(s['reference'],s['grows'],None);c.frozen_weights=frozen
    original_weights=dict(frozen.weights);original_signs=dict(frozen.senses)
    full=frozen.elastic_master(s['compact'],s['grows']);rowgen=ActiveRows(s,set(range(193)),full)
    rowgen.seed=artificial_point(full,np.zeros(1))[0];native=SimpleNamespace(seed='old_dual')
    new,rows=c.apply(s,rowgen,native,frozen.elastic_master,lambda master,x:artificial_point(master,x)[0],tmp_path/'apply')
    assert frozen.weights==original_weights and frozen.senses==original_signs
    assert set(np.flatnonzero(new['compact'].rhs!=s['compact'].rhs))=={0}
    assert new['compact'].matrix is s['compact'].matrix and native.seed is None
    assert new['compact'].rhs[0]-s['compact'].rhs[0]==pytest.approx(-.0189)
    lower,upper=c.bounds(0,1);assert lower[0]==.8836 and upper[0]==1.1025
    assert c.bounds(1,1)[0][0]==.9025 and not c.gains and c.previous is None
    assert validate_execution(c.report())
    assert LOWER_DELTA==F(-189,10000) and UPPER_DELTA==F(211,10000)


def test_original_p1_body_is_byte_identical_after_composition():
    from v42_a_stage_canary import phase
    original=inspect.getsource(phase.run);ns=dict(phase.run.__globals__)
    rowgen=compile_phase(phase.run,ns);compiled=compile_conditional(rowgen,ns,None)
    marker='    # Original P1:'
    assert inspect.getsource(compiled).split(marker)[1]==original.split(marker)[1]
