# Conditional external production recovery

This is preparation, not an additional solve. Registered M0 sources and the active LP remain unchanged. No production root may start while the exact registered M0 PID/script/worktree is alive.

If M0 finishes with certified nodes, import the complete queue and all basis/proof receipts, preserving both children. If M0 has an unresolved numerical root, preserve its failed attempt and transfer its identical unfixed root domain to the production queue. A recovered attempt is a fresh LP attempt with unchanged scientific model, never a resumed native solver tree.

M0 already shows severe crossover cleanup infeasibility (up to 1e13) and intermediate rho outside its original [0,1] bound after over 2,700s. If an external fallback is needed after backend selection, use **cold dual simplex Method=1** for the root recovery, capped at 1800s, then valid parent basis/dual simplex Method=1 for children, capped at 900s. This changes the LP algorithm only; original A/RHS/bounds/axis/minimize-rho objective remain identical. Limits are further clipped to the immutable overnight deadline. A TIME_LIMIT/NUMERIC LP produces no new certified LP bound and stays OPEN.

Every five minutes during an LP, save the current in-flight OPEN checkpoint; also save after every node. Checkpoint SHA, fixing history, exact original-domain dual/Farkas certificate recomputation and failed-attempt archive hashes guard restart. Explicit recovery is required for a crashed attempt. All prior attempt bytes are archived before a new one; no domain is removed.

Measured child uplift builds directional pseudocosts. Use deterministic score, fractionality, node_activity/charge_mode tie-break and column index. This affects branch choice only. Branch both 0 and 1; exact proof alone authorizes pruning. Strong-branch probing is omitted when the currently measured LP cost makes extra probes unjustified.

A rational root infeasibility certificate that conflicts with a full replay-PASS incumbent is treated as an authority/numerical conflict. It does not silently close the scientific problem.
