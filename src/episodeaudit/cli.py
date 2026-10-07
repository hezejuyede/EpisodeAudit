"""Command-line entry points with deterministic UTF-8 JSON reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .episodes import build_episodes
from .integrity import audit_integrity
from .manifest import AuditInputError, group_key, load_manifest, manifest_from_rows, write_manifest
from .metrics import evaluate_predictions, load_predictions
from .sampling import sample_indices


def _json_write(report: dict, output: str | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(rendered)


def _load_json(path: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuditInputError(f"Unable to read JSON input: {error}") from error
    if not isinstance(value, dict):
        raise AuditInputError("Lineage JSON must contain an object.")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="episodeaudit", description="Evidence-aware manifest, sampling exposure, and grouped prediction checks.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="Check membership, supplied groups/hashes, raw files, and optional declared fitting lineage.")
    audit.add_argument("manifest")
    audit.add_argument("--verify-files", action="store_true")
    audit.add_argument("--data-root")
    audit.add_argument("--train-split", action="append")
    audit.add_argument("--test-split", action="append")
    audit.add_argument("--validation-split", action="append")
    audit.add_argument("--lineage")
    audit.add_argument("--group-policy", choices=("unspecified", "disjoint", "overlap_allowed"), default="unspecified")
    audit.add_argument("--require-pass", action="store_true", help="Return 3 for UNKNOWN and 1 for FAIL; supplied evidence never implies actual execution verification.")
    episodes = commands.add_parser("episodes", help="Build explicit timestamp-derived acquisition proxies.")
    episodes.add_argument("manifest")
    episodes.add_argument("--gap-seconds", type=float, default=5.0)
    episodes.add_argument("--naive-timezone")
    episodes.add_argument("--overwrite-groups", action="store_true")
    episodes.add_argument("--manifest-output", required=True)
    sampling = commands.add_parser("sample", help="Generate deterministic matched-budget sample indices and complete group exposure counts.")
    sampling.add_argument("manifest")
    sampling.add_argument("--n-draws", type=int, required=True)
    sampling.add_argument("--strategy", choices=("image", "group", "episode"), default="image")
    sampling.add_argument("--seed", type=int, default=0)
    sampling.add_argument("--image-replace", action="store_true")
    sampling.add_argument("--split", action="append")
    metrics = commands.add_parser("metrics", help="Evaluate fixed predictions with an explicit optional bootstrap unit.")
    metrics.add_argument("predictions")
    metrics.add_argument("--manifest")
    metrics.add_argument("--class", dest="classes", action="append")
    metrics.add_argument("--bootstrap", type=int, default=0)
    metrics.add_argument("--seed", type=int, default=0)
    metrics.add_argument("--unit", choices=("image", "group"), default="image")
    metrics.add_argument("--confidence", type=float, default=0.95)
    metrics.add_argument("--stratify", action="store_true")
    metrics.add_argument("--probability-map", help="JSON object mapping each class label to its probability CSV column.")
    metrics.add_argument("--decision-rule", choices=("argmax",))
    demo = commands.add_parser("demo", help="Write a small explicitly synthetic software-test fixture and reports.")
    demo.add_argument("directory")
    for command in (audit, episodes, sampling, metrics, demo):
        command.add_argument("--output", help="JSON report path; default is stdout.")
    return root


def create_demo(directory: str | Path) -> dict:
    """Synthetic bytes and labels for software smoke testing, not field data."""
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    raw = base / "raw"
    raw.mkdir(exist_ok=True)
    rows = []
    for split, count in (("train", 8), ("test", 6)):
        for index in range(count):
            sample = f"{split}-{index}"
            payload = f"SYNTHETIC SOFTWARE TEST ONLY / {sample}\n".encode("utf-8")
            (raw / f"{sample}.txt").write_bytes(payload)
            rows.append({"sample_id": sample, "collection_id": "synthetic-fixture", "label": "A" if index < count / 2 else "B",
                         "group_id": f"{split}-g{index // 2}", "group_kind": "episode", "split": split,
                         "sha256": hashlib.sha256(payload).hexdigest(), "path": f"{sample}.txt"})
    manifest = manifest_from_rows(rows)
    write_manifest(manifest, base / "manifest.csv")
    predictions = [{"sample_id": r["sample_id"], "collection_id": r["collection_id"], "y_true": r["label"],
                    "y_pred": r["label"] if i % 3 else ("B" if r["label"] == "A" else "A")}
                   for i, r in enumerate(rows) if r["split"] == "test"]
    with (base / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("sample_id", "collection_id", "y_true", "y_pred"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(predictions)
    lineage = {"allowed_source_collections": ["synthetic-fixture"], "stages": [
        {"name": "synthetic-fit", "purpose": "fit", "fit_sample_ids": [{"collection_id": r["collection_id"], "sample_id": r["sample_id"]} for r in rows if r["split"] == "train"]},
        {"name": "synthetic-predict", "purpose": "transform", "uses_labels": False, "sample_ids": [{"collection_id": r["collection_id"], "sample_id": r["sample_id"]} for r in rows if r["split"] == "test"]}]}
    _json_write(lineage, str(base / "lineage.json"))
    reports = {
        "integrity": audit_integrity(manifest, verify_files=True, data_root=raw, lineage=lineage, group_policy="disjoint"),
        "sampling": sample_indices(manifest, 4, strategy="episode", splits=("train",), seed=7),
        "predictions": evaluate_predictions(predictions, manifest=manifest, bootstrap=100, unit="group", seed=7),
    }
    for name, report in reports.items():
        _json_write(report, str(base / f"{name}.json"))
    return {"schema_version": "1.0", "audit": "demo", "data_kind": "synthetic_software_test_only",
            "integrity_status": reports["integrity"]["status"], "n_rows": len(rows),
            "files": ["manifest.csv", "predictions.csv", "lineage.json", "integrity.json", "sampling.json", "predictions.json"],
            "warning": "This demonstration provides no new disease, field, or independent-collection evidence."}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "audit":
            report = audit_integrity(load_manifest(args.manifest), verify_files=args.verify_files, data_root=args.data_root,
                                     train_splits=args.train_split or ("train",), test_splits=args.test_split or ("test",),
                                     lineage=_load_json(args.lineage) if args.lineage else None, group_policy=args.group_policy,
                                     validation_splits=args.validation_split or ("validation", "val"))
        elif args.command == "episodes":
            manifest = build_episodes(load_manifest(args.manifest), gap_seconds=args.gap_seconds,
                                      naive_timezone=args.naive_timezone, overwrite_groups=args.overwrite_groups)
            write_manifest(manifest, args.manifest_output)
            report = {"schema_version": "1.0", "audit": "episode_construction", "n_rows": len(manifest),
                      "n_episodes": len({group_key(r) for r in manifest.rows}), "gap_seconds": args.gap_seconds,
                      "time_evidence_counts": dict(sorted(Counter(r["episode_time_basis"] for r in manifest.rows).items())),
                      "identity_evidence": "UNKNOWN", "limitation": "Timestamp episodes are acquisition proxies; no specimen identity is inferred."}
        elif args.command == "sample":
            report = sample_indices(load_manifest(args.manifest), args.n_draws, strategy=args.strategy, seed=args.seed,
                                    image_replace=args.image_replace, splits=args.split)
        elif args.command == "metrics":
            report = evaluate_predictions(load_predictions(args.predictions), manifest=load_manifest(args.manifest) if args.manifest else None,
                                          classes=args.classes, bootstrap=args.bootstrap, seed=args.seed, unit=args.unit,
                                          confidence=args.confidence, stratify=args.stratify,
                                          probability_columns=_load_json(args.probability_map) if args.probability_map else None,
                                          decision_rule=args.decision_rule)
        else:
            report = create_demo(args.directory)
        _json_write(report, args.output)
        if args.command == "audit" and args.require_pass:
            return {"PASS": 0, "FAIL": 1, "UNKNOWN": 3}[report["status"]]
        return 0
    except (AuditInputError, OSError) as error:
        failure = {"schema_version": "1.0", "status": "ERROR", "error_type": type(error).__name__, "message": str(error)}
        try:
            _json_write(failure, args.output)
        except OSError:
            # An unwritable report path must not trigger a second traceback.
            # stdout is the explicit fallback so a caller can still capture JSON.
            _json_write(failure, None)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
