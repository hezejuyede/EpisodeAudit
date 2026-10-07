# Optional local UCI HAR application

This release contains our aggregate software outputs, not original or derived
HAR window rows. The source is the official free [UCI dataset](https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones),
DOI [10.24432/C54S4K](https://doi.org/10.24432/C54S4K).

The current UCI record states **CC BY 4.0**, while the actual original ZIP
README and `.names` notice say **“Any commercial use is prohibited.”** This
discrepancy remains unresolved. MIT covers our software and does not replace
upstream data rights. Review both notices and determine whether your local use
is permitted before opting in. The scripts reject both downloading and
processing without the explicit `--opt-in-upstream-data` flag. Opt-in does not
resolve public redistribution rights.

No original ZIP, sensor vectors, subject/activity vectors, source notices,
window manifests, prediction rows or member-level traces are included in this
release or submission package. Optional processing writes all such local
material only below `replayed_results/har`, which is ignored and must be
excluded from every ZIP and public commit. Do not copy these local outputs into
the release. The bundled `reported_results/HAR_APPLICATION_PUBLIC_SUMMARY.json`
contains only aggregate counts and our software decisions, with no participant
ID list or original window rows.

## Local reproduction

Install the core package and optional metadata application dependencies:

```shell
python -m pip install -e .
python -m pip install -r scripts/requirements-har.txt
```

After reviewing the notices and confirming your own permitted local use,
explicitly request the official source:

```shell
python scripts/download_har_local_source.py --opt-in-upstream-data
python scripts/run_har_application.py --prepare-only --opt-in-upstream-data
python scripts/record_har_execution.py --opt-in-upstream-data
python scripts/build_har_public_aggregate.py --opt-in-upstream-data
```

The optional downloader uses the official UCI URL, a 600-second bound, and the
ignored `replayed_results/har/source_cache` directory. A separately acquired
copy of the recorded official archive may be placed there instead. The
application checks its 61,005,872-byte size and recorded SHA-256, then full
outer/inner ZIP CRC and each retained metadata member. A changed upstream
artifact is rejected rather than silently substituted for the reported data.
This is a locally recorded checksum, not an authenticated checksum published by
UCI. The server's absent HTTP Content-Length remains UNKNOWN.

`run_har_application.py --audit --opt-in-upstream-data` uses the current frozen
eight-module runtime. `record_har_execution.py` additionally records the
application assertion events that actually execute. Counts apply to that
replay and are separate from earlier software validation receipts. Expected
UNKNOWN and intentional FAIL outcomes remain in the outputs.

The optional figure uses only the bundled public aggregate and needs no source
download or opt-in:

```shell
python -m pip install -r scripts/requirements-figures.txt
python scripts/plot_har_workflow.py
```

Its S1 PNG/PDF and provenance are written to the ignored `figures` directory.

## What the application establishes

The official source has 10,299 repeated windows from 30 supplied participants:
7,352/2,947 train/test windows, 21/9 participants and no shared participant IDs.
Set and crosstab oracles agree. Our explicit training-only row ShuffleSplit
fault shares all 21 training participants; it is not the original UCI protocol.

The joined software demonstration observes UNKNOWN/PASS/FAIL changes when the
task is specified, a constructed overlap violates the task, membership is
restored, a transform split is missing/restored, or held-out labels are declared
for a transform. These are supplied metadata/declaration checks. Raw sample
verification, physical identity truth and unobserved actual execution remain
UNKNOWN. The original/repaired aggregate audit is therefore not a universal
leakage-free certificate.

The training-majority constant rule, selected without test labels, has
six-class BA=1/6; actual scikit-learn and analytic metric oracles agree. Its
subject bootstrap demonstrates correct joining/resampling, not a useful new
sensor classifier. The image and group allocation settings have different
replacement rules and do not establish training or prediction advantages.
This application does not add newly recruited participants, prospective user
adoption, field/pathology validation or algorithm superiority.

The two added transform controls were planned after the initial HAR results
were available. Their exploratory timing is retained in
`provenance/HAR_PROTOCOL_PLANS.json`; they are not retrospectively described as
preregistered.

## Attribution

Dataset citation uses the official UCI creator order: Reyes-Ortiz J, Anguita D,
Ghio A, Oneto L, Parra X. *Human Activity Recognition Using Smartphones*.
UCI Machine Learning Repository; 2013. DOI 10.24432/C54S4K.

The archive additionally requests the original paper: Anguita D, Ghio A,
Oneto L, Parra X, Reyes-Ortiz JL. *A Public Domain Dataset for Human Activity
Recognition Using Smartphones*. ESANN 2013 proceedings; 2013. p. 437–442.
[Official conference index](https://www.esann.org/proceedings/2013) and
[original publisher PDF](https://www.esann.org/sites/default/files/proceedings/legacy/es2013-84.pdf).
Its title is not used to override the archive's rights notice. The dataset
and conference-paper author orders differ; no unverified DOI is supplied for
the conference paper.
