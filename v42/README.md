# Submission semantic boundary

This branch imports three existing V42 boundary modules because the Runtime-v14R2 base does not contain the V42 package. Their source hashes are in `docs/runtime_vnext15_reproducible_semantic/V42_INTERFACE_BASE_SNAPSHOT.json`. Existing policy functions, runtime-unavailable behavior and physics are unchanged. This is an integration boundary, not a complete copy of the external V42 application.

`SubmissionRuntimeRequest` accepts an optional redacted `SubmissionSemanticPayload`, its original submission observation timestamp, and `SEM_COOCCUR32_V1` version. Existing requests without those fields remain valid. A frozen `SemanticFeatureAdapter` transforms the payload identically in offline replay and future inference. Its current historical whitelist is `user` and `submit_line`; other optional interface concepts are not active model features.

`SemanticArrivalAdapter` attaches numeric features to an arrival whose scheduling duration already has independent authority. Its cache retains the submission vector while the job runs. It neither changes a duration nor fits a model. `UnboundRuntimeProvider` continues to return unavailable when no runtime model has passed the required gates.

`cc4_augmented_input` appends only observed past semantic state to the existing hourly CC4 inputs. C2 can use `FrozenSemanticClusters` with saved centers and an independently verified SHA256 digest. No future job payload or online transformer fit is required. With the feature flag disabled, the original input object is returned unchanged.

All defaults are OFF. `require_selected_model` requires the selected-model and complete-gate flags separately from feature availability. Callability is not operational model authorization. Historical anonymized identifiers and future raw identifiers occupy separate namespaces; automatic identity alignment is not claimed. See the final verdict and privacy contract before using a research bundle.
