# Episode identity authority

The raw archive schema has `id`, scheduler `job_id`, `array_pos`, `array_range`, submission/start/end and state fields. No explicit restart/requeue attempt counter is available in the audited schema. Scheduler/array fields do not themselves establish a new attempt. The inherited GPU-H100 scanner enforces unique normalized `id`; its source_job_hash links archive/member/row/UID. All canonical rows retain this source fingerprint and snapshot hash.

Identity is therefore a conservative **source-record/submission episode observed continuously in adjacent authoritative snapshots**, not a permanent UID-home assertion. PENDING→RUNNING remains the same episode if the newly observed start is after the preceding issue and no later than the current issue. RUNNING continuation requires identical already observed execution start. A missing intermediate observation, source/submission change without attempt evidence, state regression or changed execution start is unresolved, not an inferred completion/requeue. The immutable reference is retained, and native use fails closed. No future completion timestamp enters this contract.

Explicit attempt_id is supported only alongside a causal authority hash and observed timestamp. A different attempt observed after the preceding issue establishes a new episode that may receive a new site. These optional fields are **not populated for the Kestrel regression dataset**, since that authority is absent. Tests exercise them with explicit fixtures, not invented historical labels.

The episode ID uses UID + observed submission seconds + explicit attempt ID under the versioned contract. Archive/content hash is never a preference seed or episode-reset permission. A changed provenance fingerprint during an alleged continuation triggers unresolved authority. This separates reproducible source integrity from data-dependent numerical placement.

The raw source shows an accounting-record workload, not observed AIDC geography. No conclusion is made that hidden scheduler retries within one raw record can be recovered. See EPISODE_SOURCE_FIELD_AUDIT.json and REFERENCE_GENERATOR_INPUT_AUDIT.json.
