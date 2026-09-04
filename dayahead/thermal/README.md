# V24T thermal-aware AIDC

This namespace identifies the measured NLR ESIF IT-to-overhead response and
transfers only its normalized temporal shape to a Melbourne-equivalent AIDC
case. It is not a measured Melbourne cooling model.

The immutable baseline is `C0_CONSTANT_PUE_FROZEN_BASELINE`, with
`P_PCC = 1.30 * P_IT`. C1 is weather-dependent and quasi-static. C2 adds a
strictly causal stable thermal state. Melbourne transfer uses
`REFERENCE_PUE_ENERGY_NORMALIZATION` so the IT-energy-weighted overhead ratio
remains exactly 0.30 without adding an extra PUE multiplier.

The runner never calls workload models, scaling code, grid objectives,
OpenDSS, or final B0/B1/B2/B3 science.

Create the isolated environment and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dayahead\thermal\requirements-v24t.txt
.\.venv\Scripts\python.exe -m dayahead.thermal.bundle --all
```

GFS range downloads are cached only below the configured raw-data root. The
runner downloads `.idx` files first, writes a volume preflight, and refuses to
download if the selected byte ranges exceed 20 GiB.
