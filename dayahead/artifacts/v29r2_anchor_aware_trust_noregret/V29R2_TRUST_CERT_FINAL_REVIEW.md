# V29R2 Trust Certification Final Review

Status: **PASS**

The trust selection gate used only Fresh OpenDSS model fidelity and the frozen C1 one-percent authority. Absolute anchor and candidate violations are retained in the diagnostic artifact and were not selection inputs.

Fresh execution: 630 trajectories and 60,480 sequential slot solves; April rows used: 0.

- rho=0.10: PASS; fidelity=True; C1=True; max voltage error=1.22031011e-05 pu; max current error=6.2247056e-05 pu.
- rho=0.25: PASS; fidelity=True; C1=True; max voltage error=1.22439555e-05 pu; max current error=8.35830695e-05 pu.
- rho=0.50: PASS; fidelity=True; C1=True; max voltage error=1.24349267e-05 pu; max current error=0.000113476389 pu.
- rho=1.00: PASS; fidelity=True; C1=True; max voltage error=1.32769886e-05 pu; max current error=0.000495863724 pu.

V29R2 selected rho_AIDC=1.00 using a freshly rerun pre-April certification under the prospectively frozen V29R2 contract.
