# V24M factor predictability and oracle ceiling review

- Primary bottleneck: `BURST_OCCURRENCE`
- Direct LightGBM Mean WAPE: `0.992099083212`
- Factorized LightGBM Mean WAPE: `0.975338653379`
- Factorization better than direct: `true`

Oracle values are explicitly non-causal diagnostics and are excluded from every production feature and selection path.
