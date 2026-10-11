# All-stage physical and matrix census

Raw is an analytic census of the accepted physical time graph before the existing forward reachability screen. PhysicalPrescreen is the saved FULL matrix after that existing screen. Additional proposed physical exclusions are 0. Dense is a structural prediction awaiting Source18 integrated readback. No solver/model reconstruction or optimization points were used.

| Stage | Rows | Columns | Binary | NNZ | Arc | Stay | Travel | Node bin | Mode bin | Pch | Pdis | Q | SOC | PCS rows | GridAux |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Raw | 1,136,364 | 352,365 | 214,888 | 16,472,984 | 214,504 | 9,216 | 205,288 | 0 | 384 | 9,216 | 9,216 | 9,216 | 388 | 147,456 | 109,440 |
| PhysicalPrescreen | 1,130,336 | 344,967 | 208,312 | 16,432,980 | 207,928 | 8,942 | 198,986 | 0 | 384 | 8,942 | 8,942 | 8,942 | 388 | 143,072 | 109,440 |
| Compact | 1,139,374 | 354,005 | 9,422 | 16,650,042 | 207,928 | 8,942 | 198,986 | 9,038 | 384 | 8,942 | 8,942 | 8,942 | 388 | 143,072 | 109,440 |
| Security | 852,277 | 354,005 | 9,422 | 11,224,163 | 207,928 | 8,942 | 198,986 | 9,038 | 384 | 8,942 | 8,942 | 8,942 | 388 | 143,072 | 109,440 |
| Static | 802,026 | 339,387 | 9,322 | 8,842,298 | 207,736 | 8,750 | 198,986 | 8,938 | 384 | 8,942 | 8,942 | 8,942 | 380 | 143,072 | 95,122 |
| C3A | 730,486 | 339,387 | 9,322 | 8,609,710 | 207,736 | 8,750 | 198,986 | 8,938 | 384 | 8,942 | 8,942 | 8,942 | 380 | 89,420 | 95,122 |
| Dense | 715,596 | 354,277 | 9,322 | 7,911,369 | 207,736 | 8,750 | 198,986 | 8,938 | 384 | 8,942 | 8,942 | 8,942 | 380 | 89,420 | 110,012 |

## Per MESS retained domain

| Stage | MESS | Arc | Stay | Travel | Node bin | Mode bin | Pch | Pdis | Q | SOC | PCS rows |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Raw | MESS01 | 53,626 | 2,304 | 51,322 | 0 | 96 | 2,304 | 2,304 | 2,304 | 97 | 36,864 |
| Raw | MESS02 | 53,626 | 2,304 | 51,322 | 0 | 96 | 2,304 | 2,304 | 2,304 | 97 | 36,864 |
| Raw | MESS03 | 53,626 | 2,304 | 51,322 | 0 | 96 | 2,304 | 2,304 | 2,304 | 97 | 36,864 |
| Raw | MESS04 | 53,626 | 2,304 | 51,322 | 0 | 96 | 2,304 | 2,304 | 2,304 | 97 | 36,864 |
| PhysicalPrescreen | MESS01 | 51,922 | 2,233 | 49,689 | 0 | 96 | 2,233 | 2,233 | 2,233 | 97 | 35,728 |
| PhysicalPrescreen | MESS02 | 51,994 | 2,236 | 49,758 | 0 | 96 | 2,236 | 2,236 | 2,236 | 97 | 35,776 |
| PhysicalPrescreen | MESS03 | 52,066 | 2,239 | 49,827 | 0 | 96 | 2,239 | 2,239 | 2,239 | 97 | 35,824 |
| PhysicalPrescreen | MESS04 | 51,946 | 2,234 | 49,712 | 0 | 96 | 2,234 | 2,234 | 2,234 | 97 | 35,744 |
| Compact | MESS01 | 51,922 | 2,233 | 49,689 | 2,257 | 96 | 2,233 | 2,233 | 2,233 | 97 | 35,728 |
| Compact | MESS02 | 51,994 | 2,236 | 49,758 | 2,260 | 96 | 2,236 | 2,236 | 2,236 | 97 | 35,776 |
| Compact | MESS03 | 52,066 | 2,239 | 49,827 | 2,263 | 96 | 2,239 | 2,239 | 2,239 | 97 | 35,824 |
| Compact | MESS04 | 51,946 | 2,234 | 49,712 | 2,258 | 96 | 2,234 | 2,234 | 2,234 | 97 | 35,744 |
| Security | MESS01 | 51,922 | 2,233 | 49,689 | 2,257 | 96 | 2,233 | 2,233 | 2,233 | 97 | 35,728 |
| Security | MESS02 | 51,994 | 2,236 | 49,758 | 2,260 | 96 | 2,236 | 2,236 | 2,236 | 97 | 35,776 |
| Security | MESS03 | 52,066 | 2,239 | 49,827 | 2,263 | 96 | 2,239 | 2,239 | 2,239 | 97 | 35,824 |
| Security | MESS04 | 51,946 | 2,234 | 49,712 | 2,258 | 96 | 2,234 | 2,234 | 2,234 | 97 | 35,744 |
| Static | MESS01 | 51,874 | 2,185 | 49,689 | 2,232 | 96 | 2,233 | 2,233 | 2,233 | 95 | 35,728 |
| Static | MESS02 | 51,946 | 2,188 | 49,758 | 2,235 | 96 | 2,236 | 2,236 | 2,236 | 95 | 35,776 |
| Static | MESS03 | 52,018 | 2,191 | 49,827 | 2,238 | 96 | 2,239 | 2,239 | 2,239 | 95 | 35,824 |
| Static | MESS04 | 51,898 | 2,186 | 49,712 | 2,233 | 96 | 2,234 | 2,234 | 2,234 | 95 | 35,744 |
| C3A | MESS01 | 51,874 | 2,185 | 49,689 | 2,232 | 96 | 2,233 | 2,233 | 2,233 | 95 | 22,330 |
| C3A | MESS02 | 51,946 | 2,188 | 49,758 | 2,235 | 96 | 2,236 | 2,236 | 2,236 | 95 | 22,360 |
| C3A | MESS03 | 52,018 | 2,191 | 49,827 | 2,238 | 96 | 2,239 | 2,239 | 2,239 | 95 | 22,390 |
| C3A | MESS04 | 51,898 | 2,186 | 49,712 | 2,233 | 96 | 2,234 | 2,234 | 2,234 | 95 | 22,340 |
| Dense | MESS01 | 51,874 | 2,185 | 49,689 | 2,232 | 96 | 2,233 | 2,233 | 2,233 | 95 | 22,330 |
| Dense | MESS02 | 51,946 | 2,188 | 49,758 | 2,235 | 96 | 2,236 | 2,236 | 2,236 | 95 | 22,360 |
| Dense | MESS03 | 52,018 | 2,191 | 49,827 | 2,238 | 96 | 2,239 | 2,239 | 2,239 | 95 | 22,390 |
| Dense | MESS04 | 51,898 | 2,186 | 49,712 | 2,233 | 96 | 2,234 | 2,234 | 2,234 | 95 | 22,340 |

All four MESS and all 96 operating slots have numeric records in ALL_STAGE_PER_MESS_96_SLOT_METADATA.csv; SOC/node terminal96 records remain separate. Static substitutes the eight endpoint SOC variables by exact fixed constants; all380 interior SOC variables and384 charge modes remain.

Raw delta over FULL: +6,028 rows, +7,398 columns, +6,576 binary, +40,004 NNZ. These are source/incidence-derived scalars, not a saved raw matrix. Native presolved family axes are unknown because no actual presolved matrix/name map was exported.
