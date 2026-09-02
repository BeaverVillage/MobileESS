# V29R2 Executable-Service Model Card

Authority: `CARRYIN_EXECUTABLE_SERVICE_V1`
Status: **PASS**

The model is a deterministic two-stage LightGBM hurdle model. It uses only request and queue fields observable at the D-1 18:00 fixed-AEST cutoff. Start and end timestamps are label-only fields and never enter the feature matrix. No April submit or label row is used for fitting or calibration.

H_REQ is the request envelope. H_NOM is the nominal executable-service estimate. H_LOW is a one-sided conformal lower bound calibrated on rolling-origin daily aggregate errors. The required invariant is `0 <= H_LOW <= H_NOM <= H_REQ`.

- Rolling evaluation days: 20
- Rolling evaluation cohort-days: 32
- Aggregate H_LOW coverage: 0.906250 (target 0.90)
- Sharpness H_LOW/H_NOM: 0.182081
- Nominal MAE: 75.516581 node-h
- Nominal WAPE: 0.951897
- Nonzero lower-bound cohort-days: 7

The model is not tuned on April performance and does not use final state, nodes used, wallclock used, nodelist, future sharing, or post-cutoff Actual as a feature.
