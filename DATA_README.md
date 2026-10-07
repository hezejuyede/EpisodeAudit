# Released inputs and replay coverage

| Directory | Contents | What can be reproduced |
|---|---|---|
| `data/synthetic` | Frozen artificial CSV faults, known-truth receipt, declared fitting examples, three tiny artificial byte files, and documented post-first-run validation expansion | Membership/group/digest findings, missing-evidence status, raw-byte checks, fitting declarations, and low-budget exposure accounting |
| `data/derived` | Two wheat direction manifests and fixed prediction tables, two factual COIL manifests, and an anonymous acquisition-size ledger | Retrospective class metrics, conditional image-unit intervals, explicit probability consistency, group-protocol differences, and sampling allocation |
| `reported_results` | Previously executed numeric output tables and two wheat interval reports | Comparison targets; archived timings and external-library outputs are not new measurements from the default replay |
| `provenance` | Canonical source hashes, copy/adaptation ledger, sanitized validation summary, and recorded SVC decision-rule interpretation | Version consistency, documented transformations, and the exact scope of the previously reported execution |

After installing the package from this checkout:

```sh
python -m unittest discover -s tests -v
python scripts/replay_released_data.py
```

The default replay uses relative repository paths, NumPy, 2,000 class-stratified image-unit bootstrap replicates, and recorded seeds. It compares all 180 frozen software fixtures, fixed wheat class counts/metrics/intervals, and six sampling allocations against released reference outputs. Missing wheat plant IDs and raw-file verification remain unknown. It also demonstrates COIL group overlap under disjoint, overlap-allowed, and unspecified protocols.

The U0 ledger is aggregate derived input. Opaque identifiers preserve group ordering and sizes without exposing original collection days, folder codes, or per-image identities. Artificial expansion reproduces allocation mathematics only. No source pixels, representations, model-training data, plant IDs, or pathology diagnoses are reconstructed.

Optional controls use additional environments:

```sh
# In a separate environment with the recorded scikit-learn version:
python -m pip install -r scripts/requirements-scikit-controls.txt
python scripts/replay_scikit_controls.py

# In a distinct Python 3.12 environment for the pinned Deepchecks stack:
python -m pip install -r scripts/requirements-deepchecks-controls.txt
python -m pip install --no-deps .
python scripts/replay_deepchecks_controls.py
```

The optional external-library scripts are authored wrappers, not copied libraries. They require separate installations and respect the license boundaries in `DATA_RIGHTS.md`. Different environments can change elapsed time. No throughput superiority is inferred.

Raw COIL verification is optional because original images are not distributed:

```sh
python scripts/download_coil20_for_local_use.py --destination local-coil20
python scripts/replay_released_data.py --coil-raw local-coil20/images
```

The download script checks the original archive fingerprint. It downloads only when explicitly run and does not grant a right to republish the images. Without a separately obtained raw directory, the COIL metadata/group checks run, while raw-content verification remains unknown.

No default replay downloads data, fits a classifier, re-diagnoses disease, or supplies third-party certification. Image-unit intervals cannot be described as independent-plant or future-collection confidence intervals. Public immutable release and author/institutional release approval remain pending for this local candidate.

## Article figure replay

```sh
python -m pip install -r scripts/requirements-figures.txt
python scripts/plot_article_figures.py
```

The optional generator uses only `reported_results/wheat_replay_class_metrics.csv`, `reported_results/sampling_oracle_results.csv`, and `reported_results/wheat_U0_software_sampling_replay.csv`. It writes the three main figures and graphical abstract as PNG/PDF plus a provenance JSON in `figures/`. All inputs and output paths are relative to the checkout. Matplotlib is outside the core dependency list. The local review recorded four PNGs identical to the original article artwork; PDF metadata can vary. The public candidate includes the script and inputs, while the generated files and SHA comparisons are retained in the separate local release review.

## Exact finite group-bootstrap reference

Four artificial fixed-prediction configurations test unequal and mixed groups, stratification, and an absent truth class. The independent rational-arithmetic enumerator checks the finite distributions and class-support conditioning. It is not a population coverage study.

```sh
python scripts/check_exact_bootstrap.py
```

## Corrective rerun and finite-oracle coverage

The current software has 55 behavioral test methods. Four defects discovered after the initial freeze were corrected: label-consuming transforms require known permitted partition roles; grouped consumers reject conflicting same-key kind metadata; nonfinite numeric IDs/labels cannot be converted into artificial strings; and episode replacement requires a boolean flag. Consistently unknown group kinds remain explicitly resampleable with unknown evidence. Old failure records remain in `validation/`; these are post-discovery regressions, not preregistered or third-party certification.

Current `results/` records identify the rerun of 453 assertions, 117 addendum cases, 12 installed CLI commands and 180 selected original-library comparisons. `validation/exact_bootstrap/` records 53 checks on four fully enumerated small synthetic resampling distributions. Run `python scripts/check_exact_bootstrap.py` to replay that finite reference comparison. The 53 checks add no real observations or population-coverage experiment. Receipt hashes for raw execution files and sanitized public counterparts are labelled separately; `provenance/SOURCE_COPY_LEDGER.json` distinguishes current source/output digests from historical initial-copy digests.

## Optional HAR aggregation and upstream rights

Only aggregate HAR summaries/audit statuses are public. Window arrays, source ZIPs, original notices and per-window traces are not included. The original UCI page's CC BY 4.0 statement conflicts with the downloaded archive's commercial-use prohibition; that conflict is not resolved by the MIT software license. Default commands without `--opt-in-upstream-data` stop before download/data generation. Optional commands in README write upstream-derived local outputs under ignored `replayed_results/har` and require separate acceptance of applicable upstream terms. See `docs/HAR_REPRODUCTION_AND_RIGHTS.md`. Aggregate task counts and a simple baseline illustrate the audit interface, not new recognition accuracy or independent-domain validity.
