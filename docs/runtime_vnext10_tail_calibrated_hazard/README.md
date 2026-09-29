# Runtime-vNext10 — diagnostic only

Selected: T3_LOGISTIC_STATIC / G1 / LAST_RATE, CPU4 training. **NOT PROMOTED.**
See FINAL_REVIEW_KO.md for the 32-question Korean review and FINAL_VERDICT.json for phase-specific gates.

The standalone RUNTIME_PROVIDER requires Python, numpy, pandas, scipy, scikit-learn and lightgbm. Exact tested versions are in EXECUTION_ENVIRONMENT.json.
Add the RUNTIME_PROVIDER directory to sys.path and import RuntimeProvider from provider:

    provider = RuntimeProvider(allow_research=True)
    result = provider.predict_total({
        'job_id': 'unseen-example', 'num_gpus_req': 4, 'num_nodes_req': 1,
        'num_cores_req': 32, 'requested_memory_mib': 262144,
        'requested_seconds': 14400, 'array_index': None,
        'qos': 'unknown', 'partition': 'unknown', 'account': 'unknown'
    }, event_time='2025-04-02T00:00:00Z')

predict_remaining takes the same job record plus elapsed_seconds; no completion truth is allowed.
All request descriptors remain Kestrel_trace_proxy, never strictly verified production features.
The final calibration state is frozen before April and never updates from April outcomes.
