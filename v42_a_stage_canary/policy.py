from v42_a_stage_lexcases.policy import ROOT,OUT as OVERNIGHT,STATIC as OVERNIGHT_STATIC,POLICY as MAY19_POLICY
OUT=OVERNIGHT/'CANARIES'
STATIC=OVERNIGHT_STATIC/'CANARIES'
DAY=None
DAYS=('2025-05-17','2025-05-10','2025-05-12')
POLICY=dict(MAY19_POLICY,schema='A_PRACTICAL_CANARIES_NO_RETUNING_V1',same_completed_algorithm=True,dates=DAYS,row_promotion_after=19,activation_batch=64,stagnation_rounds=3,stagnation_fraction=.01)
