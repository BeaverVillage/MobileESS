# 과거 실패와의 비교

|Previous PR|Previous failure cause|New architecture difference|Measured improvement|
|---|---|---|---|
|#152|Incomplete exact pricing/convergence;1604columns, certified interval[0.5687115725336208,0.5741861223241257]|No pricing or trajectory-column enumeration; original compact axes retained|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|
|#158/159|Grid-only generation and one-tree callbacks gave no certified bound gain; root remained stalled|All96-slot physics and original grid retained, actual new integer-valid temporal SOC inequalities|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|
|#167|Tested local hulls:320rows, certified LB unchanged|All4 MESS / all96-slot movement arcs, global endpoint SOC consequences; no local-window EF|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|
|#169|4-slot/two-block joint hulls gave certified gain0; UB improved independently|No 2.397M trajectory pattern enumeration or replicated window;651small sparse original-variable rows|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|
|#179|Cold exact children:median197.566s, no certified node-floor gain, gap9.82%|ROOT-strengthening before B&B; no repeat child LP campaign without material gate|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|
|#182|133254/225952addedcolumns and312931/1001388addedrows; ROOT TIME_LIMIT|Addedcolumns0; addedrows651; addednnz1302|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|
|#183|Weak20cuts inactive atnewmaster, first recourse120s unresolved|Full96slot SOC/P/Q/PCS/energy incompactmaster, no giant recourse solve loop|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|

각 PR의 실제 head와 description을 PR_REFERENCE artifacts에 보존했다. PR169의 UB 개선을 LB 개선으로 해석하지 않는다. 새로운 full-domain exact pricing 구조의 실용성을 증명하지 못했으므로 pricing 대안은 개발하지 않았다.
