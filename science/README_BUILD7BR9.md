BUILD7BR9 — LOSSLESS CACHE/INDEX ACCELERATION

BR8 is the golden model. BR9 implements only A1-A8 caching/index/precompute/logging changes. Before optimize(), after the identical BR8 warm start, Gurobi Fingerprint and model counts must exactly match BR8: fingerprint 0x24b788bc; variables 151810; rows 92202; qrows 8180; nonzeros 609618; binaries 110489. No Gurobi model reuse, matrix API rewrite, new pruning, parameter change, warm-start change, physical relaxation, or objective change. Obj5 remains 1.5%.
