V40S5R1 executes the user-registered causal expanding-origin protocol. It has no operational scheduler consumer.

The execution order is `prepare`, preregistration commit, `run development`, candidate selection commit, `run exposed`, `diagnostics`, tests, scientific commit, final receipt commit, and read-only verification. The driver advances only through the exact 36 issue times in the inherited panel.

All quantile and final residual estimators reuse the resolved S5 L2 configuration. Auxiliary residual crossfit median estimators reuse S5's separately frozen L0. There is no hyperparameter search. The current issue's evaluation labels cannot be loaded through the label reader until both P and P-W prediction files have been written and their hashes verified.

Artifacts are stored under `dayahead/artifacts/v40s5r1_rolling_origin_runtime/`. Each `membership/` file contains all causally eligible unique historical rows for an origin. Each `models/<origin>/<track>/` directory contains deterministic gzip model files, preprocessing, OOF evidence, and a package manifest. Prediction files contain no start/end/runtime labels. Scored files are separate. Event logs establish the order of reads, fits, prediction hashes, and scoring.

The available Python environment is `C:/codex_mobileess_workspace/v40s2_runtime_env/Scripts/python.exe`, with the frozen LightGBM dependency directory `C:/codex_mobileess_workspace/v40s3_runtime_packages` on PYTHONPATH. OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, and MKL_NUM_THREADS are set to 1. Versions are recorded in the compute artifacts.

For a read-only integrity check of the completed worktree:

```powershell
$env:PYTHONPATH='C:\codex_mobileess_workspace\v40s3_runtime_packages'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
& 'C:\codex_mobileess_workspace\v40s2_runtime_env\Scripts\python.exe' -B -m dayahead.v40s5r1.closeout verify
```

To run the contract tests without rewriting the committed JUnit report or creating a pytest cache:

```powershell
& 'C:\codex_mobileess_workspace\v40s2_runtime_env\Scripts\python.exe' -B -m pytest -q tests/dayahead/test_v40s5r1_core.py tests/dayahead/test_v40s5r1_evidence.py -p no:cacheprovider
```

The closed worktree is evidence. Do not overwrite its model packages or predictions, or use its results to select a new model family, quantile, coefficient, feature set, window policy, or runtime experiment.
