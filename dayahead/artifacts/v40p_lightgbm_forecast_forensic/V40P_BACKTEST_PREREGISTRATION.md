# V40P preregistration

The JSON is the exact registered specification. Three non-overlapping folds: September 2024, November 2024, March 2025. Freeze the original architecture, 177 features, objectives, fitted tree counts, seeds and 0.5 arrival scale. No result-driven refit changes. Causal failures in the original input construction are retained and reported, not repaired. Diagnostic results do not validate those inputs.

Primary: MAE skill against zero arrivals and fixed-state persistence. UTC daily block bootstrap, 2,000 replicates, seed 20260906. Burst cutoffs use each fold training targets only.
