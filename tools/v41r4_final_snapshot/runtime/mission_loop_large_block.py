"""Whole-job neighborhoods may exceed the nominal packing target atomically."""
from v41r4_loop_budget import adapted, OriginalBoundedLex, LoopBoundedLex

choose = adapted(OriginalBoundedLex._choose, [
    ("        if size>10000:raise RuntimeError('COMPLETE_JOB_BLOCK_EXCEEDS_MAX_FREE_DISCRETE:'+str(g))",
     "        # A complete first job is indivisible; allow it to exceed the nominal packing target."),
    ('MAX_FREE_DISCRETE=25000 if coupled else 10000,complete_job_domains_opened=True,',
     'MAX_FREE_DISCRETE=max(25000 if coupled else 10000,count),complete_job_domains_opened=True,\n'
     '            nominal_max_free_discrete=25000 if coupled else 10000,actual_free_discrete=count,\n'
     '            oversized_complete_groups=[g for g in selected if len(self.decision_groups[g])>10000],\n'
     '            oversized_job_rule="COMPLETE_ATOMIC_JOB_NO_CANDIDATE_PRUNING",')
])

def install():
    LoopBoundedLex._choose = choose
