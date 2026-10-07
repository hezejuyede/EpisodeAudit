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

On Windows with file-path length limits, unpack to a short folder and keep pip's temporary path short. A failed build can leave a staging directory; retry from a fresh checkout. The local release review preserves the initial long-path build failure and the successful fresh-build run.

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

## Local release candidate and complete replay

This checkout includes the frozen eight runtime modules, 43 behavioral tests, synthetic fault fixtures, licensed wheat-derived tables, factual COIL manifests, and an anonymous acquisition-size ledger. It excludes original images, private correspondence, other submitted manuscripts, model weights, local environments, and third-party library source or binaries.

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
