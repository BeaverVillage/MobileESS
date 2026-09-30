# Independently reproduced original full-May matrix

Columns 7,920,701; rows 9,358,534; nonzeros 100,455,768. Binary 2,796,366; general integer 0; continuous 5,124,335. Matrix build used the complete 1,499-job native domain and all 96 electrical slots, without optimize. Build seconds during VHD compaction are not clean performance measurements.

Runtime completion: 34,923,402 nonzeros across 1,152 rows; maximum 77,795 terms at R1121 (zero-based matrix row 1121). Non-scientific tie: 14,503,274 nonzeros across 273,614 rows. Full row distributions and unique-column incidence/objective participation are in the baseline CSVs.

Inherited PR102 measured initial MIP root relaxation: 1,557.90 s, 457,124 iterations, objective 0.6716023396111563. Presolved rows/columns/nonzeros: 7,533,647 / 7,247,816 / 46,376,330. Its 3,600-s production run had one node and no incumbent; the evidence demonstrates root processing dominance, not branch-tree explosion. Matrix families identify compression opportunities but do not establish that any one family caused a particular number of solve seconds. Fresh continuous-P1 LP diagnostics will be measured only after the clean performance gate. Their total LP optimize wall includes LP presolve and is distinguished from the inherited MIP root-only time.
