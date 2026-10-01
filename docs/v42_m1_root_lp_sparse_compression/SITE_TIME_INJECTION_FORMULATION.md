# Site/time injection bindings

F1 introduces 24*96 P and 24*96 Q continuous unrestricted auxiliaries. P_MESS[s,t] equals the sum of each unit's discharge minus charge at that site/time; Q_MESS[s,t] equals the sum of individual reactive power. Every equality uses the original expressions returned by the unchanged native constructor, including unreachable terms already zero under PR106 exact forward reachability.

Only the fixed-anchor grid consumes these auxiliaries. Individual connected-state bounds, charge mode, inner16 PCS, arcs, SOC and travel energy remain untouched. The original 208,312 binary variables remain free. The PR106 incumbent is a start, never a bound or equality restriction.

F0 reproduced 138,620,454 nonzeros. Its grid repeatedly expanded Pch/Pdis 91,291,680 times and Q 45,665,364 times. F1's complete matrix has 25,222,123 nonzeros, including the injection equalities. See the family census and repetition audit for measured counts.
