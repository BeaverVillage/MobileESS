"""Actual failing model sizes, unchanged ordinary packing, and full-group coverage."""
from types import SimpleNamespace
import copy
from fast_prepare import read, ROOT, record
from dayahead.paper_analysis.storage import write_json
from v41r4_loop_budget import OriginalBoundedLex
from mission_loop_large_block import choose
from v41r4_loop_runtime import MAY_OUT
import dayahead.v41.physics_ranking as ranking

def engine(sizes):
    return SimpleNamespace(control=None,iteration=0,decision_groups={g:list(range(n)) for g,n in sizes.items()},
        visits={g:0 for g in sizes},stage_counts={g:0 for g in sizes},structure={},metadata={},
        previous_groups=[],target_free=5000,structure_ref=None)

def main():
    original=ranking.reorder
    ranking.reorder=lambda self,ordered,anchors:(ordered,anchors)
    tests=[]
    try:
        for sizes in ({0:20,1:40,2:5000},{0:10000,1:300},{0:4999,1:1,2:2}):
            a=engine(sizes);b=copy.deepcopy(a)
            before,meta=OriginalBoundedLex._choose(a,0);after,updated=choose(b,0)
            assert before==after and all(updated[k]==v for k,v in meta.items())
        tests.append('ORDINARY_SELECTION_AND_METADATA_UNCHANGED')
        evidence=read(MAY_OUT/'mission/BLOCK_SIZE_MODEL_EVIDENCE.json')
        assert evidence['group301_size']==11970
        a=engine({301:11970,302:200})
        try:OriginalBoundedLex._choose(a,0)
        except RuntimeError as e:assert str(e)=='COMPLETE_JOB_BLOCK_EXCEEDS_MAX_FREE_DISCRETE:301'
        else:raise AssertionError('ORIGINAL_ERROR_NOT_REPRODUCED')
        selected,meta=choose(a,0)
        assert selected==[301] and len(a.decision_groups[301])==11970
        assert meta['actual_free_discrete']==meta['MAX_FREE_DISCRETE']==11970
        tests.append('ACTUAL_11970_VARIABLE_GROUP_OPENS_COMPLETE')
        a=engine({0:4000,301:11970,302:27000,303:100})
        opened=set()
        for _ in range(8):
            selected,meta=choose(a,0);assert selected
            assert meta['actual_free_discrete']==sum(len(a.decision_groups[g]) for g in selected)
            for g in selected:a.visits[g]+=1;a.stage_counts[g]+=1;opened.add(g)
        assert opened==set(a.decision_groups)
        tests.append('OVERSIZED_GROUPS_NOT_STARVED_OR_TRUNCATED')
        # Runtime installation is shared by B1 and B3's same LoopBoundedLex class.
        from mission_loop_large_block import install
        from v41r4_loop_budget import LoopBoundedLex,LoopBudget
        install();assert LoopBoundedLex._choose is choose
        assert LoopBudget(1800).total==1800
        tests.append('B1_A1_SHARED_REPAIR_AND_1800_BUDGET_PRESERVED')
    finally:ranking.reorder=original
    result=dict(status='PASS',tests=tests,model_evidence=record(MAY_OUT/'mission/BLOCK_SIZE_MODEL_EVIDENCE.json'))
    write_json(MAY_OUT/'mission/LARGE_BLOCK_REPAIR_TEST.json',result)
    print(result)

if __name__=='__main__':main()
