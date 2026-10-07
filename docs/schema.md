# Input and evidence contract

## Manifest

The input is a comma-separated UTF-8 or UTF-8-BOM CSV. Header names are unique and have no surrounding whitespace. Required IDs are nonempty strings. Optional values may be empty. Scalar values are stripped of surrounding whitespace; textual IDs are not converted to integers. Control characters and malformed CSV field counts are rejected. Extra columns are preserved.

The in-memory API rejects numerical `NaN` and positive/negative infinity before string conversion. Use `None` or an empty string for missing optional values; required IDs and prediction labels remain mandatory. Literal strings such as `"nan"` are preserved as strings rather than guessed to be missing. This rule prevents dataframe missing values from creating artificial group IDs or truth classes.

| Field | Meaning |
|---|---|
| `sample_id` | A unique record/view identifier within one collection. |
| `collection_id` | The collection namespace for membership keys. |
| `label` | Optional supplied class, never an independently verified diagnosis. |
| `group_id` | Optional grouping identifier for repeated records. |
| `group_kind` | `identity`, `episode`, `other`, or `unknown`; absent kind becomes `unknown`. |
| `group_namespace` | Optional explicit namespace shared across collections. Without it, group IDs are collection-local. |
| `sha256` | Optional 64-character hexadecimal string. A supplied string is unverified until raw bytes are actually hashed. |
| `split` | Explicit partition. Default integrity comparison uses `train` and `test`; custom name sets may be supplied. |
| `path` | Relative path under the explicit `data_root`, used only when file verification is requested. Absolute paths and resolved paths outside this root are refused. |
| `timestamp` | ISO-8601 capture date and time. Offset required unless a naive-time-zone assumption is explicitly supplied. |
| `acquisition_id` | User-provided session/folder key required for episode construction. Its truth is not inferred. |

Membership key: `(collection_id, sample_id)`.

Group key without an explicit namespace: `("collection", collection_id, group_id)`.

Group key with an explicit namespace: `("explicit", group_namespace, group_id)`.

`group_kind` deliberately does not change the key. Contradictory kinds for one namespace/ID are a failure, so relabeling a group cannot evade overlap checking. Bare IDs equal across two collections do not merge automatically. Different collection-local group keys do not prove that the underlying specimens differ.

A group ID with missing kind can reveal a supplied overlap, but cannot obtain a complete group-check pass. A namespace or kind without a group ID is malformed. Repeated membership keys are kept for auditing rather than silently deduplicated. Sampling, episode construction, and prediction joining require unambiguous membership.

Integrity, sampling and grouped prediction calculations share the same conservative group-kind consistency rule. Multiple recorded kinds for one namespace/ID, including a mix of `unknown` and a known kind, are unresolved metadata: integrity reports failure and group consumers reject that selection. Groups whose kinds are consistently `unknown` remain usable for explicit group sampling/bootstrap, with `group_evidence_status=UNKNOWN`. A `PASS` for group evidence describes complete supplied metadata, not verified identity or specimen independence.

## Integrity report

Each check states its evidence basis:

- `membership`: supplied record IDs; duplicate or cross-split records fail.
- `groups`: supplied namespace/group IDs and kinds under an explicit group-overlap policy. `disjoint` treats cross-split groups as a violation; `overlap_allowed` reports overlap without calling it a protocol failure. Default `unspecified` keeps protocol status unknown. Contradictory kinds fail regardless of policy.
- `provided_hashes`: supplied hash strings; repeated strings across selected splits fail this declared-evidence check.
- `label_consistency`: supplied hash strings and labels across the complete manifest; one digest with conflicting labels fails. It does not identify the correct label.
- `raw_content`: SHA-256 computed from accessible raw bytes; byte-content overlaps and supplied/computed mismatches fail. Missing paths, unreadable files, and unperformed hashing cannot pass.
- `declared_lineage`: explicitly supplied fitting declarations; absent evidence is `UNKNOWN`.

`PASS` means a listed check has sufficient supplied evidence and no detected violation. `FAIL` means a detected violation within its stated basis. `UNKNOWN` means no violation was detected but evidence is incomplete. Failures take precedence over unknowns. The aggregate status is a conjunction of the listed checks; it does not cover unobserved training behavior, near-duplicate visual content, specimen identity, or pathology.

`identity_evidence.status` and `execution_leakage.status` remain `UNKNOWN`. Even a complete computational audit does not independently establish these facts. Unassigned split rows keep selected split-integrity claims incomplete.

The group-overlap policy must correspond to the actual research question. Known-object recognition from new views can reuse object IDs legitimately. New-specimen generalization requires group-disjoint membership if trustworthy specimen IDs exist. Specifying `disjoint` for heuristic episodes only tests episode disjointness, not specimen disjointness. Missing group intent cannot be filled in from a classifier's accuracy.

## Fitting lineage JSON

```json
{
  "allowed_source_collections": ["source"],
  "stages": [
    {
      "name": "source-scaler",
      "purpose": "fit",
      "fit_sample_ids": [{"collection_id": "source", "sample_id": "s01"}]
    },
    {
      "name": "target-inference",
      "purpose": "transform",
      "uses_labels": false,
      "sample_ids": [{"collection_id": "target", "sample_id": "t01"}]
    }
  ]
}
```

Purposes: `fit`, `model_selection`, `calibration`, `threshold`, `transform`. Stage names are unique. Fit members must be in an allowed source collection and a declared training split. Selection/calibration/threshold members may be in declared training or validation splits of an allowed source. Default names are `train`, `validation`/`val`, and held-out `test`; custom disjoint name sets are propagated consistently to the lineage checker. Held-out membership fails even in an allowed source collection. A transform stage may read target records if it explicitly declares `uses_labels=false`; target/held-out label use fails. A missing label-use declaration is unknown. Members are two-field objects to avoid ambiguity from joining IDs with delimiters. Empty member lists are unknown rather than vacuously passing. Unknown or ambiguous manifest members fail.

The declaration is not a runtime trace. Users must retain their actual training configuration, source-only selection logic, and development history separately. Historical target peeking cannot be excluded from these records.

For `uses_labels=true` transform stages, a member must also have a declared training or validation split. A missing or unrecognized split role is `UNKNOWN`; observed target/held-out label use remains a failure. `uses_labels=false` permits label-free inference access without inventing a partition role.

## Sampling and metrics

Sampling indices refer to the original manifest order. Image sampling defaults to a uniform shuffle without replacement; `image_replace=true` uses independent replacement draws. Group/episode sampling draws a supplied group uniformly, then one of its members uniformly, with replacement. Episode sampling additionally requires `group_kind=episode` on every selected record. Other grouping types use `strategy=group`.

Exposure counts include every provided group, including zero counts. The population-standard-deviation CV is undefined (`null`) when the mean exposure is zero or grouping is incomplete. Spearman correlation uses average ranks for ties and is undefined for constant input. Expected group exposures are reported to distinguish allocation mathematics from an empirical model effect.

Predictions require `sample_id`, `y_true`, `y_pred`, optionally `collection_id`. Without a manifest, IDs can support a descriptive report but not group resampling. With a manifest, every prediction resolves to one member and any provided manifest label must agree with `y_true`. Classes are strings. Recalls for classes absent from `y_true` are `null`; balanced accuracy averages only observed truth classes and reports this rule.

Optional probabilities require an explicit class-to-column mapping. Each declared class has one distinct column; each row has finite values in [0,1] summing to one within 1e-6. Nonnumeric, missing, nonfinite, invalid-range, incomplete-class, or invalid-sum inputs are rejected. Probability numeric validity can pass; calibration is not assessed. The decision-rule check remains unknown unless `argmax` is explicitly declared. Under that declaration a predicted class must be a tied or unique maximum. SVC decision predictions need not use probability argmax; the tool does not change supplied predictions to enforce an undeclared rule.

Bootstrap resampling can use individual prediction rows or complete provided groups. The model and its predictions are held fixed. Group bootstrap does not imply independent specimens. Class-stratified group bootstrap requires homogeneous groups. With unstratified sampling, class-metric intervals are conditional on replicates that retain all original truth classes; counts of excluded replicates are reported. No interval estimates future independent-collection variation.
