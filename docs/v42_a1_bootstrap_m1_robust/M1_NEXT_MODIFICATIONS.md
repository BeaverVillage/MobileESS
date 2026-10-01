Measured classification: ROOT_LP.

Required physics fixes: preserve fail-closed independent route, charge mode, SOC, PCS and grid checks. No automatic repair or voltage fallback.

Exact computational candidates: profile the measured dominant phase before proposing equivalent sparse matrix construction, row ordering or validated warm-start reuse. PR101 native additional route reduction was 0%; no speculative pruning campaign.

Optional tuning: separately preregister a bounded single-thread comparison only after review; none performed here.

For the measured ROOT_LP case, prioritize exact site/time injection bindings: net MESS P and Q auxiliaries equal to unchanged sums of unit Pdis-Pch and Q, with frozen affine grid rows bound to those auxiliaries. Retain all individual route, mode, Pch/Pdis/Q, SOC, PCS and grid limits. The current matrix has 138,620,454 nonzeros; repeated expanded injections are an inspection target, not a measured speedup claim. Require projection/equivalence proof, independent validation and a structural census before a future benchmark. No such model change is applied here.

Scientific changes require explicit authorization: voltage margin, job/domain, CC4/Runtime, PCS, SOC, graph/time/energy, terminal conditions, or objectives. No post-result changes applied.
