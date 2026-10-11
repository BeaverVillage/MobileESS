# Why current Exact C3A is larger than PR162

Every saved matrix entry was counted. Historical C3A: 582,808 rows / 306,040 columns / 9,322 binaries / 5,351,612 NNZ. Current C3A: 984,680 / 353,601 / 9,326 / 12,379,878. The exact increase is 401,872 rows, 47,561 columns, 4 binaries, and 7,028,266 NNZ.

## Full NNZ attribution

| Row family | Current minus historical C3A NNZ |
|---|---:|
| NormalAmps | +664,971 |
| line_thermal_face | +292,490 |
| node_activity_link | +100 |
| response_line_P_binding | +1,144,761 |
| response_line_Q_binding | +1,144,507 |
| response_line_correction_binding | -475 |
| response_transformer_P_binding | +398,676 |
| response_transformer_Q_binding | +694,330 |
| transformer_kVA | +348,416 |
| voltage_lower | +1,431,365 |
| voltage_upper | +909,125 |

## Causes supported by source and actual tensors

1. Hardware adds 33 transformer phases and 33 physical voltage nodes. Old branch axes are 263 lines + 120 transformer phases; current axes are the same 263 lines + 153 transformer phases. The old physical voltage axis has 386 nodes; current has419. All 33 new branch phases are enumerated in the JSON.
2. LDC project() duplicates the 419-node axis into 838 endpoint entries. The two voltage-matrix halves are bitwise identical, while endpoint constants can differ. The original builder therefore produces 80,448 upper and80,448 lower rows. Exact Static Presolve already reduces each to40,128; this LDC duplication is already absorbed and does not alone explain the final gap.
3. Old flow P/Q tensors come from the original lossless full-grid binding. Current model.py independently measures voltage/current/flowP/flowQ central secants after native AUTO/TIME control prefixes. The actual current line P/Q bindings each have about49 stored entries including their auxiliary, versus about4.8 originally. New nonzero cross-control responses and loss/control sensitivities make these tensors dense. The line branch count is unchanged. No tiny coefficient was discarded.
4. Dense transformer responses activate the existing exact cost gate for every153 transformer phase per slot: current14,688 P and14,688 Q auxiliaries versus576 each historically before presolve. Historical static presolve aliases/fixes many sparse repeated line and transformer responses. Current dense independently measured tensors do not have those identical definitions. Exact identical-auxiliary detection is present; the source inputs differ.
5. PR160 security screening is missing from the current sequence. The current static pass absorbs exact constants and duplicate/proportional rows, but omits the route/PQ/SOC affine-support certificates used by old PR160/161. Current C3A explicitly keeps all grid security rows. Thus current retains14,682 NormalAmps rows,234,812 transformer faces,402,432 line faces, and80,256 voltage rows. Old C3A retains0 /35,790 /324,871 /30,336 respectively. Historical IDs cannot be applied to new hardware, tensors, or RHS.
6. Original fixed AIDC input differs: old accepted A1 Planning versus current independent B2 input. The named60-control axis is identical, but1,050 of1,152 fixed AIDC entries differ, with max54.7723975641307 kW change. Fixed AIDC changes constants/RHS and redundancy margins. For a fixed tensor it does not enlarge MESS coefficient support; the tensor regeneration explains the density change.
7. The original route/PCS/SOC/mode/energy-balance and injection-definition blocks have identical saved coefficient support, coefficient values, RHS, senses and row names. Current retains4 extra source node_activity binaries because historical build.py source-flow bound propagation was not called before static presolve.
8. Historical F0 begins after an older exact75,455-row reduction: its raw model was961,472 rows. In particular historical F0 kVA110,592 is already73,728 below raw184,320. Current raw kVA235,008 equals153×96×16. Comparing235,008 to110,592 without accounting for baseline deletions overattributes growth to hardware.

## What is preserved

The current local PR162 pass really removes53,652 PCS faces,17,884 connected-Q rows and4 terminal-location rows, totaling71,540 rows and232,588 NNZ. It keeps every column and independently tightens109,234 affine bounds. Thus the C3A name is real for the local reductions, but does not imply complete PR160 security-reduction reuse.

ALL_ROW_FAMILIES.md and ALL_COLUMN_FAMILIES.md include every original/C2/C3A family count and NNZ for both sources. MODEL_GROWTH_AND_INPUT_AXES.json includes exact tensor support counts, all axes, original physical-block bitwise checks and SHA evidence. No solver was executed by this audit; no Root180 performance claim is made.
