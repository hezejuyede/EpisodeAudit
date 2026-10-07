# EpisodeAudit

EpisodeAudit is a small Python library and command-line tool for auditing the evidence available in grouped evaluation data. It links a dataset manifest, optional fitting declarations, sampling exposures, and fixed predictions through explicit collection/sample keys. It reports unsupported integrity claims as `UNKNOWN` rather than converting missing evidence into a pass.

The software can be used with image collections or other repeated-measurement records. It does not require a neural network, download pretrained weights, or fit a disease classifier. The included synthetic demonstration tests software behavior; it is not a new biological dataset.

## What the software checks

- Repeated collection/sample memberships, reported cross-split groups under an explicit overlap policy, and conflicting group metadata.
- Overlapping supplied SHA-256 strings separately from SHA-256 hashes computed from accessible raw files.
- Conflicting labels attached to the same supplied digest, including within one split.
- Declared fitting, model-selection, calibration, and threshold membership against allowed source collections and held-out split names.
- Timestamp-derived acquisition episodes, using an explicit acquisition key, gap rule, and provided timestamp offsets or recorded time-zone assumptions.
- Matched-budget image or group sampling, with all supplied groups included in exposure diagnostics even when they receive no draws.
- Class-wise errors and image- or group-unit percentile bootstrap intervals for fixed predictions.
- Numeric probability checks under an explicit class-to-column mapping; an argmax decision rule is checked only when declared.

These checks concern the supplied evidence. A temporal episode does not identify a plant, leaf, patient, or object. An identity label is user-provided metadata, not verified identity. Exact-content hashes do not detect perceptual near-duplicates. Fitting declarations do not prove what an unobserved training program executed or whether developers inspected target outcomes in the past. These limitations are included in the JSON reports.

## Installation

Python 3.10 or later is required. NumPy is the only runtime dependency.

```sh
python -m pip install .
python -m episodeaudit --version
python -m unittest discover -s tests -v
```

For a source-only run without installation, add the repository's `src` directory to `PYTHONPATH`. The supplied CI workflow tests Python 3.10, 3.11, and 3.12 on Linux; a local Windows run does not imply that a remote CI run has occurred.

## First run

```sh
episodeaudit demo demo-output
episodeaudit audit demo-output/manifest.csv --verify-files --data-root demo-output/raw --lineage demo-output/lineage.json --group-policy disjoint --output demo-output/audit-again.json
episodeaudit sample demo-output/manifest.csv --split train --n-draws 4 --strategy episode --seed 7 --output demo-output/exposure-again.json
episodeaudit metrics demo-output/predictions.csv --manifest demo-output/manifest.csv --bootstrap 1000 --unit group --seed 7 --output demo-output/metrics-again.json
```

The demo writes artificial text bytes and artificial labels. Its raw content is created locally for a smoke test. `integrity.status=PASS` in this complete demo means that the listed computational checks pass; `execution_leakage` and `identity_evidence` still remain `UNKNOWN`.

## Manifest and prediction inputs

The manifest is a UTF-8 CSV with required `sample_id` and `collection_id` fields. IDs are strings, scoped to their collection. An example is:

```csv
sample_id,collection_id,label,group_id,group_kind,split
image-01,source,A,episode-01,episode,train
image-02,target,A,episode-02,episode,test
```

Optional fields are `label`, `group_id`, `group_kind`, `group_namespace`, `sha256`, `split`, `path`, `timestamp`, and `acquisition_id`. Extra fields are retained. Empty evidence remains missing. The full schema and status meanings are in [docs/schema.md](docs/schema.md).

A prediction CSV requires `sample_id,y_true,y_pred`. Add `collection_id` whenever a sample ID is not globally unique. With a manifest, every prediction must resolve to exactly one member and any supplied manifest label must agree with `y_true`. Repeated predictions cannot be silently pooled. Supply a declared class list if the report must also show classes absent from the evaluated rows.

```sh
episodeaudit metrics predictions.csv --manifest manifest.csv --class healthy --class disease --bootstrap 2000 --unit group --stratify --seed 17 --output prediction-audit.json
```

Class-stratified group bootstrap requires class-homogeneous groups. Mixed-label groups cannot be silently split. Unstratified bootstrap reports the number of replicates missing an originally observed truth class; class-metric intervals exclude those replicates and explicitly state that conditioning.

## Python API

```python
from episodeaudit import load_manifest, audit_integrity, sample_indices
from episodeaudit import evaluate_predictions, load_predictions

manifest = load_manifest("manifest.csv")
integrity = audit_integrity(manifest, verify_files=True, data_root="raw", group_policy="disjoint")
exposure = sample_indices(manifest, 100, strategy="group", seed=17, splits=("train",))
metrics = evaluate_predictions(load_predictions("predictions.csv"),
                               manifest=manifest, bootstrap=2000,
                               unit="group", seed=17)
```

There is no hidden fallback from group bootstrap to image bootstrap. Missing group IDs raise an input error when group resampling or balancing is requested. [docs/api.md](docs/api.md) documents each function and the fitting-lineage contract.

## Reporting and reproducibility

Reports use `PASS`, `FAIL`, and `UNKNOWN` for evidence-dependent checks. A report with no raw-file verification, no fitting declaration, or no declared group-overlap policy generally cannot obtain an aggregate integrity pass. Actual execution and identity verification are outside the tool's observation regardless of this aggregate status. Each report records the evidence basis and limitations.

Group overlap is not automatically an invalid experiment. Recognizing a known object from a new camera view can legitimately reuse the object's ID across splits; evaluating new specimens requires a different protocol. The default `group_policy="unspecified"` reports overlap while returning unknown protocol status. Use `disjoint` for an explicitly group-disjoint evaluation, or `overlap_allowed` for legitimate known-object/new-view reuse. Contradictory kinds for one group key still fail either protocol. Exact byte-content reuse remains a separate check.

Unknowns need different actions: supply identifiers and the evaluation policy for group checks; supply accessible raw files for hash verification; supply complete fitting declarations for declared-source checks; and collect or review actual identity/pathology evidence outside this software. A declaration cannot resolve unobserved training execution or historical target inspection.

JSON has sorted keys, UTF-8 encoding, no timestamps, and no NaN values. The same inputs, input row order, software/dependency versions, settings, and seed produce deterministic reports. Row order affects sampling indices. Record the Python and NumPy versions when archiving a run.

CLI commands return 0 after successfully writing a report, 2 for an input/IO error, and, with `audit --require-pass`, 1 for `FAIL` or 3 for `UNKNOWN`. If the requested output path is unwritable, an error JSON falls back to stdout. These exit codes let an automated pipeline block on missing evidence without conflating it with a confirmed overlap.

When predictions contain probabilities, provide `probability_columns={"A": "prob_A", "B": "prob_B"}` in the API or a JSON mapping file through `--probability-map`. Values must be finite, in [0,1], and sum to one within 1e-6, with one distinct column per declared class. No calibration quality is inferred. Missing probability evidence is unknown. By default `y_pred` is not required to equal probability argmax; for example, an SVC can use a decision function distinct from its probability estimator. Set `decision_rule="argmax"` or `--decision-rule argmax` only if that rule was actually used. Tied maxima allow any tied class.

## Interpretation

Uniform image sampling gives larger groups greater expected exposure because they contain more records. Uniform group sampling changes that allocation by construction. The software quantifies this allocation and the resulting fixed-prediction errors; a lower exposure CV is not evidence of improved disease diagnosis. Model benefits require a separately controlled experiment with unchanged model architecture, update budget, and evaluation members.

Source cross-validation, target performance, algorithmic seeds, and independent specimen replication answer different questions. The reports do not convert image-level uncertainty into collection-level or biological uncertainty. Label conflicts identify inconsistent supplied labels, not which diagnosis is correct.

## License and release status

The new software code is released under the MIT terms in `LICENSE.txt` (identical to `LICENSE`). This license does not grant rights to third-party images, model weights, or historical datasets. Their original licenses and access conditions remain applicable.

This local version is 1.0.0. No publicly hosted software repository, release DOI, or peer-reviewed acceptance is asserted by this source directory. A companion manuscript must identify the actual archived release before submission. The code is a development of general audit components; its software tests are distinct from the historical wheat study's numerical checks.

The second exploratory API audit found input-contract defects after the first recorded validation run. Corrections require known partition roles for label-consuming transforms, share group-kind consistency checks across consumers, reject nonfinite numerical metadata/labels, and require a boolean episode-overwrite flag. Consistently unknown group kinds remain usable for explicitly requested group resampling with `group_evidence_status=UNKNOWN`; varied recorded kinds for one key are rejected. A group-evidence pass means complete supplied metadata, without certifying actual identity. Earlier validation receipts describe their original code bytes and fixtures; they are not evidence that all inputs of the corrected source have been externally validated. The corrected source has a separate freeze receipt.

## Local release candidate and complete replay

This checkout includes the frozen eight runtime modules, 55 behavioral tests, synthetic fault fixtures, licensed wheat-derived tables, factual COIL manifests, and an anonymous acquisition-size ledger. It excludes original images, private correspondence, other submitted manuscripts, model weights, local environments, and third-party library source or binaries.

After installation, run:

```sh
python -m unittest discover -s tests -v
python scripts/replay_released_data.py
python verify_release.py
```

The replay uses relative paths and compares fixed class metrics, conditional intervals, and aggregate allocation against reference outputs. It does not retrain historical classifiers or reconstruct images from counts. [DATA_README.md](DATA_README.md) lists replay coverage and optional original-library controls. [DATA_RIGHTS.md](DATA_RIGHTS.md) records upstream attribution and the data-specific license boundaries. [RELEASE_STATUS.json](RELEASE_STATUS.json) explicitly records that no remote repository, release tag, or DOI has been created.

The three article figures and graphical abstract can also be regenerated from the three deposited result tables:

```sh
python -m pip install -r scripts/requirements-figures.txt
python scripts/plot_article_figures.py
```

Matplotlib is optional and is not part of the core runtime. The script writes PNG/PDF artwork and a provenance record to `figures/`. Only paths were adapted from the article's generator; the plotting logic is unchanged. All four PNGs matched the original article files byte for byte in the recorded local environment. PDF creation metadata may differ, so no PDF byte-identity claim is made. The candidate ships the generator and its inputs; generated graphics remain separate local review artifacts.

The synthetic test plan and later expansion retain their actual chronology. Separate implementation roles within the same assistant team are not third-party certification. Passing software checks cannot establish pathology truth, specimen independence, untouched development history, or publication rank.


## Corrective validation snapshot

The corrective source passed 55 behavioral tests and the 13 previously recorded adversarial domains after repair. The later API/CLI/library reruns include 453 assertion checks, 117 addendum cases, 12 installed CLI commands, 53 finite-oracle checks on four synthetic resampling examples, and 180 selected original-library Deepchecks comparisons with 320 original RECORD entries matching. These are software executions on one Windows host; seed variants and assertions are not independent biological samples. The initial failure inputs and old/new runtime hashes are retained in `validation/` and `provenance/`; post-discovery tests are described as regression checks. Historical receipt fields refer to the snapshot when recorded, rather than asserting that later public-candidate synchronization was already complete.

Run `python validation/recheck_adversarial_domains.py` after installation for the 13 targeted corrected/control domains. Sanitized execution records are in `results/`. Final file indexing and public publication are separate pending steps.

## Exact finite group-bootstrap reference

Four artificial fixed-prediction configurations test unequal and mixed groups, stratification, and an absent truth class. The independent rational-arithmetic enumerator checks the finite distributions and class-support conditioning. It is not a population coverage study.

```sh
python scripts/check_exact_bootstrap.py
```

## Finite resampling checks and optional HAR application

`python scripts/check_exact_bootstrap.py` replays 53 checks against four completely enumerated synthetic resampling distributions. The rational-arithmetic reference is independent of EpisodeAudit's metric computation. These examples test defined conditional bootstrap arithmetic; they are zero new real observations and do not establish population coverage or independent specimen uncertainty. `results/CURRENT_VALIDATION_PROVENANCE.json` identifies the corrective rerun, while `results/INSTALLED_SOURCE_HASH_CHECK.json` records the equal source/build/wheel/installed runtime bytes. Public path-adapted receipts state their transformations explicitly.

The optional UCI HAR application releases aggregate counts and audit outcomes only. Human activity windows, source ZIPs, upstream notices and per-window traces are excluded from the public candidate. The upstream UCI page states CC BY 4.0 while the original archive's notice prohibits commercial use; this conflict remains unresolved, and the software's MIT license grants no upstream-data rights. See [docs/HAR_REPRODUCTION_AND_RIGHTS.md](docs/HAR_REPRODUCTION_AND_RIGHTS.md).

Default HAR script calls without the explicit flag stop with exit 2 before network access or data generation. Optional local-use commands are:

```sh
python scripts/download_har_local_source.py --opt-in-upstream-data
python scripts/run_har_application.py --audit --opt-in-upstream-data
```

Upstream-derived local files and individual traces are written only under ignored `replayed_results/har`. The public aggregate comparison illustrates joined membership/protocol/lineage/reporting interfaces. Its constant baseline and recorded split counts do not demonstrate a novel recognition model, independent field diagnosis, or universal software sensitivity.
