# MobileESS

Mobile energy storage system rolling-horizon optimization research code.

This branch preserves the R25R Stage-1 implementation in the byte-frozen
`R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz` and carries the R25T exact
global-bound portfolio in `science/`.
Each rolling issue has a 54-slot, five-minute horizon and commits only its first
slot. The frozen Stage-1 acceptance rule is a globally certified relative gap of
at most 3%, followed by the numerical, causal, and Fresh OpenDSS gates.

## Repository layout

- `science/`: R25T authoritative model, global-bound portfolio solver,
  contracts, proofs, and embedded historical authorities.
- `driver_r25r_stage1_resume136.py`: validates the R25P/R25Q parent chain and
  resumes the causal run at issue 136.
- `R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz`: byte-frozen science bundle used
  by the resume driver.
- `HANDOFF.md`: current runtime state, root-cause record, and next work.

Runtime outputs, frozen parent result archives, and self-extracting `.run`
packages are intentionally kept outside Git.

## R26 online controller work

The `r26/` package is a separate event-triggered hierarchical controller. It
keeps the AC-aware radial QCP dispatch and mandatory Fresh nonlinear OpenDSS h0
gate, while moving route planning to a single nonblocking asynchronous worker.
It does not weaken or replace the R25R offline 3% certificate. See
`docs/R26_ARCHITECTURE.md` and `r26/config/r26_contract.json`.
The manuscript-facing novelty boundary and experiment contract are in
`docs/R26_METHOD_REVIEW_DEFENSE.md`.

If an R25R run was interrupted after a completed POST checkpoint, do **not**
rerun `driver_r25r_stage1_resume136.py`, because that frozen driver recreates its
work directory. Use the resumable wrapper instead:

```bash
cd /path/to/MobileESS
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  driver_r25s_stage1_resume_latest.py
```

It verifies the causal chain and resumes at the first uncommitted issue. It can
be invoked again after another interruption.

R25T replaces the unlimited restricted-master search with a bounded incumbent
phase followed by the untouched original compact MIQCP. Its global lower bound
is the maximum of the exact priced-root bound and the compact model's native
Gurobi bound; the restricted-master bound remains diagnostic only. To verify
the current causal prefix without starting a solve:

```bash
MOBILEESS_R25T_PREFLIGHT_ONLY=1 \
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  driver_r25t_stage1_resume_latest.py
```

Run the new exact resume with:

```bash
/home/jaewon/miniconda3/envs/power_v61/bin/python \
  driver_r25t_stage1_resume_latest.py
```

See `docs/R25T_GLOBAL_BOUND_PORTFOLIO.md` for certificate authority, phase
transition, retry, and resume semantics.

R26 framework validation (no long solver run):

```bash
python -m r26.release_self_test
```

The included smoke adapter tests orchestration only; it is explicitly not a
physical or OpenDSS result:

```bash
python -m r26.fast_controller_driver \
  --adapter r26.smoke_adapter:create_controller \
  --config r26/config/smoke_54.example.json \
  --output /tmp/mobileess_r26_smoke --start-issue 113 --count 54
```

## Validation

Use the project WSL Python environment:

```bash
cd science
/home/jaewon/miniconda3/envs/power_v61/bin/python release_self_test.py
```

The resume driver additionally requires its exact R25P and R25Q parent runtime
archives under `~/mobile_ess_work/frozen_artifacts/`; their names and SHA-256
digests are fail-closed in the driver.
