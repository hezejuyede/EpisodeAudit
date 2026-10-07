# API reference

The public functions are imported from `episodeaudit`. Input problems raise `AuditInputError`, a subclass of `ValueError`.

| Function | Contract |
|---|---|
| `load_manifest(path)` | Read CSV into a `Manifest`; retain original row order and extra fields. |
| `manifest_from_rows(rows, columns=None)` | Validate scalar row mappings under the same manifest contract. |
| `write_manifest(manifest, path)` | Write normalized UTF-8 CSV. |
| `audit_integrity(manifest, *, verify_files=False, data_root=None, train_splits=("train",), test_splits=("test",), lineage=None, group_policy="unspecified", validation_splits=("validation", "val"))` | Return membership, policy-dependent group, supplied/computed hash, label-consistency, and declared-lineage checks. File verification requires an existing bounded data root. |
| `audit_lineage(manifest, lineage, *, train_splits=("train",), validation_splits=("validation", "val"), test_splits=("test",))` | Check the explicit JSON declaration under consistent partition names; return declared-evidence status and execution-verification unknown. |
| `build_episodes(manifest, *, gap_seconds=5.0, naive_timezone=None, overwrite_groups=False)` | Return a new manifest with timestamp-derived episode IDs. Requires explicit acquisition ID and capture times. Existing group IDs cannot be overwritten silently. |
| `sample_indices(manifest, n_draws, *, strategy="image", seed=0, image_replace=False, splits=None)` | Return deterministic original-row indices, selected member keys, every group exposure, expectations, coverage, CV, and rank correlation. |
| `load_predictions(path)` | Read a strict prediction CSV. |
| `evaluate_predictions(predictions, *, manifest=None, classes=None, bootstrap=0, seed=0, unit="image", confidence=0.95, stratify=False, probability_columns=None, decision_rule=None)` | Return a confusion matrix, class-wise metrics, supplied-group summaries, optional mapped probability checks, and optional conditional percentile intervals. |

`Manifest.rows` is a tuple of normalized dictionaries. Treat these dictionaries as read-only. To change a manifest, make new row dictionaries and call `manifest_from_rows`; do not mutate inputs during an audit.

## Episode rule

Partition captures by collection, supplied acquisition ID, and local calendar day. Sort by UTC time, breaking equal-time ties by sample ID. Start a new episode when the adjacent time gap exceeds the configured threshold. Equality remains in the same episode. Chaining is intentional: captures at 0, 4, and 8 seconds belong to one episode with a 5-second gap even though the first-to-last interval is 8 seconds. A day boundary always starts another partition. Offset-qualified timestamps are preferred. `naive_timezone="UTC"` or an available IANA name is an explicit assumption, recorded in `episode_time_basis`.

`overwrite_groups` must be a boolean. A string such as `"False"` or a numeric flag is rejected; only explicit `True` permits replacing existing groups.

IDs are deterministic truncated SHA-256 tokens of the partition and first capture; they are identifiers for this grouping rule, not a hash of specimen identity. Changing inputs/rules can change groups. An episode can mix different underlying specimens if acquisition metadata is incomplete.

## Sampling expectations

For a budget B, N records, G groups, and group size n_g:

- Uniform image sampling: expected group exposure is B * n_g / N.
- Uniform group sampling: expected group exposure is B / G.
- Per-record probability for one replacement group draw is 1 / (G * n_g).

These are properties of the defined sampler. The empirical draw-count CV uses all G counts and population standard deviation (ddof=0); zero-draw groups are retained. A single low-budget run can have substantial sampling noise. A model-level comparison requires equal budgets and a separately controlled design.

## CLI errors and determinism

Use `python -m episodeaudit --help` and command-specific help for arguments. JSON reports have sorted keys and forbid NaN. A successful report can still contain unknowns or failures. Only `audit --require-pass` converts a declared-integrity outcome to gate exit codes. Input and IO problems produce an error JSON report and exit 2. Malformed structures do not get repaired by inventing fields.

Maintain the same Python/NumPy versions and input order for byte-identical reproducibility. Include version information in the run archive rather than interpreting repeatable algorithmic seeds as independent biological replication.

## Group intent and probability declarations

`group_policy="unspecified"` is the integrity default. Overlap is reported and the protocol remains unknown. `disjoint` tests the supplied group-disjoint requirement. `overlap_allowed` supports legitimate known-object/new-view evaluations; it does not remove observed overlaps from the report. Neither setting verifies identity or specimen independence. The same split-name sets are used by integrity and its optional lineage checker.

Probability maps are mappings from class string to CSV column string. Their keys are exactly the declared class set; if `classes` is absent, the map declares that set. Numeric values and simplex sums are checked. Without a map, probability evidence is unknown. `decision_rule=None` leaves the relationship between the supplied probabilities and `y_pred` unspecified; `argmax` checks tied or unique maxima and rejects violations. Numeric consistency does not establish calibrated probabilities or honest training.
