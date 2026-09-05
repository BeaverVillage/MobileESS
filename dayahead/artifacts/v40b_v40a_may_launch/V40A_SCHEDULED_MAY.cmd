@echo off
cd /d "C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt"
set "PATH=C:\Users\kjw39\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd;%PATH%"
set "OMP_NUM_THREADS=1"
set "OPENBLAS_NUM_THREADS=1"
set "MKL_NUM_THREADS=1"
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v40b_v40a_may_launch\V40A_OPEN_MONITOR.ps1"
"C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe" -u "C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\tools\run_v40b_campaign.py" --orchestrate >> "C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v40b_v40a_may_launch\ORCHESTRATOR.log" 2>&1
exit /b %ERRORLEVEL%
