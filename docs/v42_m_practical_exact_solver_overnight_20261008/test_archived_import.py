from practical_support import *
import tempfile
from types import SimpleNamespace
from fractions import Fraction as F
import import_archived_root as imported
core=module('archived_import_fixture_core',OLD/'bb_controller.py')
def run():
    A,d,_=hc.load();identity=read(OUT/'external_production/EXTERNAL_MODEL_AUTHORITY.json')['identity']
    state=read(OUT/'external_production/OPEN_CHECKPOINT.json')['state']
    histories=state['failed_attempt_history'];selected=next(h for h in reversed(histories) if h.get('result',{}).get('partial_basis'))
    oracle=SimpleNamespace(A=A,CSC=A.tocsc(),d=d,identity=identity,binary=np.flatnonzero(d['types']=='B'),choose_branch=lambda js,x:min(js,key=lambda j:(-min(abs(float(x[j])),abs(1-float(x[j]))),j)))
    with tempfile.TemporaryDirectory() as temp:
        runpath=Path(temp);source=OUT/'external_production'/selected['archive']['archive'];dest=runpath/selected['archive']['archive'];dest.mkdir(parents=True)
        for f in source.iterdir():
            if f.is_file():(dest/f.name).write_bytes(f.read_bytes())
        atomic(runpath/'OPEN_CHECKPOINT.json',dict(state=dict(failed_attempt_history=[selected])))
        bb=core.ExactBB(identity,str(F.from_float(.5687116104049206)),str(F.from_float(.6306505800203936)),dict(fixture=True));node=bb.select();bb.begin(node)
        receipt=imported.receipt(oracle,node,runpath)
        assert receipt['archived_origin']['new_root_optimize_calls']==0 and receipt['archived_origin']['archived_completed_OPTIMAL']
        assert receipt['basis_output_SHA256']==selected['result']['partial_basis']['SHA256']
        assert receipt['archived_origin']['saved_same_domain_basis_origin']['not_node_proof']
        bb.apply(0,receipt);coverage=bb.audit();assert coverage['OPEN']==[1,2] and float(F(coverage['global_OPEN_min_LB_exact']))==.5687116104049206
        child=bb.select();bb.begin(child);unresolved=dict(identity=identity,fixing_hash=child['fixing_hash'],proof_checked=True,LP_status='UNRESOLVED',certified_LB=None,optimal_LP_certificate_PASS=False,exact_infeasibility_PASS=False,witness=None,branch_variable=None)
        bb.apply(child['id'],unresolved);assert bb.select()['id']==2 and bb.audit()['OPEN']==[1,2]
        atomic(OUT/'ARCHIVED_IMPORT_BASIS_TESTS.json',dict(PASS=True,optimize_calls=0,existing_OPTIMAL_root_certificate_recomputed=True,historical_nonpassing_primal_not_accepted_as_LB=True,same_domain_nonoptimal_basis_is_hint_only=True,basis_bytes_SHA_identical=True,both_children_preserved=True,unresolved_first_child_kept_OPEN=True,next_unprocessed_sibling_selected=True,registered_floor_not_decreased=True,UTC=stamp()))
    print('ARCHIVED_IMPORT_BASIS_TESTS_PASS_OPTIMIZE_0')
if __name__=='__main__':run()
