# Data attribution and license boundaries

The MIT license covers the new EpisodeAudit source code, tests, authored replay scripts, and artificial software-test fixtures. It does not change the licenses of NumPy, scikit-learn, Deepchecks, image collections, pretrained weights, or restricted institutional material. No third-party library source or binary is included in this repository.

## JIC and Holeta

The release candidate includes non-image manifests and retrospective numerical prediction outputs with attribution to two CC BY 4.0 deposits:

- Long M, Brown JKM, Morris RJ, Hartley M. *Wheat Disease Dataset - Small*. Zenodo, 2022. DOI: [10.5281/zenodo.7307816](https://doi.org/10.5281/zenodo.7307816). Original deposit: 999 images, five labelled categories.
- Getachew H. *WheatLeafDataset*. Mendeley Data, version 1, 2021. DOI: [10.17632/wgd66f8n6h.1](https://doi.org/10.17632/wgd66f8n6h.1). Original deposit: 407 images.

The original data and adaptations retain [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) attribution conditions. The deposited files here are derived tables, not original pixels. The historical common-class analysis retained 709 JIC and 406 Holeta records. It excluded unrelated JIC classes, one JIC same-scene record, and one duplicate Holeta healthy record; it harmonized labels to healthy, Septoria, and stripe rust. The included predictions were generated previously and are replayed unchanged. No retraining, new pathology review, untouched prospective test, or new plant identifiers are asserted. The authors' new numerical outputs and table adaptations are provided with the same CC BY 4.0 attribution terms; this does not represent new ownership of the upstream collections.

## COIL-20

Nene SA, Nayar SK, Murase H. *Columbia Object Image Library (COIL-20)*. Columbia University Technical Report CUCS-005-96, February 1996. [Official collection page](https://www.cs.columbia.edu/CAVE/software/softlib/coil-20.php).

Included COIL files are factual manifests: published filenames, object/view IDs, assigned software-test splits, and author-computed checksums. They describe 20 objects and 1,440 processed views. The original images and downloaded archive are excluded because an explicit raw-image redistribution license has not been verified. No MIT or CC license is asserted for those excluded pixels. The optional download script retrieves the official archive for separate local use and checks its recorded SHA-256; users must respect the original provider's access and use conditions. Metadata disclosure does not confer permission to republish images.

Shared object IDs can be legitimate for known-object recognition from new views. They violate a declared unseen-object/group-disjoint protocol. The examples keep those two questions separate.

## Restricted U0 illustration

Only an anonymous group-size ledger is supplied: 2,444 acquisition-proxy groups representing 29,529 timestamped records, partitioned into 2,200 training and 244 diagnostic groups. The ledger contains opaque group IDs, split roles, and counts. It excludes original dates, folder/session strings, per-image IDs, paths, timestamps, hashes, representations, pixels, plant identities, and pathology labels.

The replay script expands these counts into explicitly artificial bookkeeping records to reproduce sampling allocation. These records are not reconstructed images, new collected data, or biological replicates. Aggregate exposure calculations require the sizes and order of groups; reproducing historical model training would require additional controlled source material that is not provided or claimed publicly accessible.

The institutional raw archive and its release-authority documentation remain outside this repository. The final publication of this aggregate derived ledger remains part of the authors' release review; no institutional permission for raw-image redistribution is invented.

## External comparators

Reported scikit-learn controls used the original library; an optional authored wrapper can rerun them on metadata. Scikit-learn is separately installed under its own BSD license.

Reported Deepchecks controls used version 0.19.1 and selected original exact-row/index checks. Its source states AGPL v3 or later. The optional authored benchmark wrapper imports a separately installed distribution, verifies its installation record, and uses public APIs. It does not copy, modify, embed, or redistribute that library. The wrapper is outside the installed EpisodeAudit core. Users installing or distributing third-party software must follow its own license. The benchmark compares selected operations and explicit adapters, not all Deepchecks capabilities or universal software superiority.

## Release status

This is a local public-release candidate. No repository has been created or pushed, no DOI has been assigned, and no immutable public availability is asserted. Final publication requires author review of this file list and explicit authorization. The code's MIT terms and the data-specific boundaries above must accompany any approved release.
