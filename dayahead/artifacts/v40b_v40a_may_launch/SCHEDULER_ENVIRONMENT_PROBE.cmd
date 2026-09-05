@echo off
cd /d "C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt"
set "PATH=C:\Users\kjw39\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd;%PATH%"
set "OMP_NUM_THREADS=1"
set "OPENBLAS_NUM_THREADS=1"
set "MKL_NUM_THREADS=1"
"C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe" "C:/codex_mobileess_workspace/tmp/v40b_scheduler_environment.py" --child > "C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v40b_v40a_may_launch\scheduler_environment.log" 2>&1
