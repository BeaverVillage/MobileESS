# Chosen representation

The isolated experiment keeps the original native mixed-sense LP, native bounds, all variables, and all physical rows. The primal transformation is the identity bijection; no standard-form variable split is needed because exact equality-multiplier completion already resolves every free-column support failure. Every 81,216 free column has a structurally triangular original equality pivot +1.

Certificate completion is dual algebra, not a changed primal LP: retain all original inequality multipliers; in reverse defining-equality order, solve the equality multiplier so its pivot free-column weighted coefficient is exactly zero. Update every affected column using exact IEEE-rational coefficients, including arbitrarily small nonzero values. Validate a newly derived rational ray independently on the original matrix. The original floating ray is never relabeled as exact-valid.

Lower-only/upper-only/boxed affine transformations are mathematically available but NOT USED. A naive free-variable split y=y_plus-y_minus is not injective (both can increase together), so it does not satisfy a literal bijection requirement. We do not claim that split is bijective. Identity preserves a literal solution-to-solution bijection and all rows without qualification.

Production row/column scaling is 2^0 (identity). Fixture-only positive power-of-two row scaling tests preserve original mapped primal vectors and objective, and exact fraction comparisons verify every coefficient/RHS scaling. No empirical normalization, bound/RHS relaxation, grid-row deletion or route restriction is used.
