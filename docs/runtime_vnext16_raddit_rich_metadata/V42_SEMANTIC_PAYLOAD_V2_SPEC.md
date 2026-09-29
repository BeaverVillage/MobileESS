# V42 semantic payload V2: research contract, not provider authorization

`SubmissionSemanticPayloadV2` additively subclasses the PR89 payload; the
candidate implementation is `semantic_payload_v2_candidate.py`. Existing V15
source is unchanged. Its authorized projection preserves legacy canonical
tokens and the existing receipt rule `observed_at <= submit_time <= issue_time`.
MINIMAL has no populated authorized fields, PARTIAL has some, and FULL has all
fields authorized by this bundle (currently user and submit_line). Every missing
field has explicit `<FIELD_MISSING>` state and categorical code -1; it is never
filled with another job's identity. Conceptual extra fields are optional but
reject non-null values until a future authority-backed revision permits them.

The tested research adapter accepts exactly `submit_time`, `observed_time`,
`namespace`, and `metadata`; the metadata object contains only the approved
fields. It delegates the existing receipt-time validation to
`SubmissionSemanticRecord`. Persisted adapter bundles contain version,
namespace, whitelist, and TRAIN category maps, and model metadata binds the
adapter SHA256. A future operational envelope would additionally need an
immutable job key, schema version, bundle digest and an attested accepted-event
capture service. That service is not implemented or certified here. Mutable
revisions must not overwrite an original receipt. Historical event timestamps
do not establish archive ingestion latency.

The currently source-supported semantic concepts inherited from V15 are `user`
and `submit_line`. Future values require the same certified identity namespace
as the fitted bundle. Unknown identities use explicit missing/unseen handling;
an unrelated archive token namespace must not be declared equal. No archive
hashing algorithm or private anonymization map is reverse-engineered.

Account, partition, QoS, job name, script, job type, work directory, array
metadata, modules and conda require a separate initial-version/capture-time and
namespace authority before they can become production predictors. Merely
including these optional concepts in a prospective schema does not authorize
their archived snapshot as a training input. RADDiT-only module/conda tokens
must not be filled into missing original Kestrel records.

The boundary accepts a sanitized categorical/numeric record, checks exact keys,
then calls the frozen TRAIN-fitted adapter. It rejects runtime, actual start/end,
queue-wait outcomes, future scheduler state, measured power and unknown keys.
Strict completed-history neighbors additionally require `end_time < submit_time`
in a separate trusted history store; end time is never a direct model input.

Raw command, script, name and path text must not be written to optimizer
artifacts. Persist only version/digest, authorized pseudonyms, numeric features
and Q50/Q90. Model loading must verify the adapter digest and categorical-feature
schema. Online refitting is not an inference requirement. Missing authority
keeps operational provider promotion disabled. Research replay/unseen tests
are reported separately and do not certify an operational capture service.

V13/R0 retains its frozen trace-proxy request/state contract. This study does not
recertify mutable requested-walltime snapshots as original submission values.
No production provider, optimizer, MESS, OpenDSS or flexibility code is changed
by this document.
