# Rollback

Use `--legacy-dense-planner` on `W02_POLICY_EPISODE_RUNNER.py` to restore the pre-acceleration dense planner and automatic presolve. For bounded diagnosis, `--benchmark-disable-fast-rack-lookup`, `--benchmark-clear-all-science-cache`, and `--benchmark-legacy-planned-replan-retry` restore the older exact paths. Rollback does not alter the site authority, canonical PRE, objective, constraints, or Fresh OpenDSS gate.
