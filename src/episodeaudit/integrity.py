"""Evidence-bounded split checks, with separate declared and computed hashes."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .manifest import AuditInputError, Manifest, group_key, membership_key


def _status(failures: bool, complete: bool) -> str:
    return "FAIL" if failures else ("PASS" if complete else "UNKNOWN")


def _split_names(values: Iterable[str], name: str, *, empty_allowed: bool = False) -> set[str]:
    if isinstance(values, str):
        raise AuditInputError(f"{name} must be a sequence of names, not a single string.")
    try:
        names = list(values)
    except TypeError as error:
        raise AuditInputError(f"{name} must be a sequence of string names.") from error
    if (not names and not empty_allowed) or any(not isinstance(s, str) or not s for s in names):
        raise AuditInputError(f"{name} must contain nonempty string names.")
    return set(names)


def _cross_overlaps(rows: list[dict[str, str]], sides: list[str], key_function) -> list[dict[str, Any]]:
    members: dict[Any, dict[str, list[dict[str, str]]]] = defaultdict(lambda: {"train": [], "test": []})
    for row, side in zip(rows, sides):
        key = key_function(row)
        if key is not None:
            members[key][side].append(row)
    findings = []
    for key, entries in sorted(members.items()):
        if entries["train"] and entries["test"]:
            findings.append({"key": list(key) if isinstance(key, tuple) else key,
                             "train_members": [list(membership_key(r)) for r in entries["train"]],
                             "test_members": [list(membership_key(r)) for r in entries["test"]]})
    return findings


def audit_integrity(manifest: Manifest, *, verify_files: bool = False, data_root: str | Path | None = None,
                    train_splits: Iterable[str] = ("train",), test_splits: Iterable[str] = ("test",),
                    lineage: dict[str, Any] | None = None, group_policy: str = "unspecified",
                    validation_splits: Iterable[str] = ("validation", "val")) -> dict[str, Any]:
    """Audit supplied split records, not unseen data or biological truth.

    PASS applies only to explicitly listed checks and their evidence basis.
    Computed raw hashes require verify_files=True and a bounded data_root.
    Supplied SHA-256 strings never certify that raw files were verified.
    """
    if not isinstance(group_policy, str) or group_policy not in {"unspecified", "disjoint", "overlap_allowed"}:
        raise AuditInputError("group_policy must be unspecified, disjoint, or overlap_allowed.")
    training = _split_names(train_splits, "train_splits")
    testing = _split_names(test_splits, "test_splits")
    validation = _split_names(validation_splits, "validation_splits", empty_allowed=True)
    if training.intersection(testing) or validation.intersection(training | testing):
        raise AuditInputError("Train/test split names must be nonempty disjoint sets.")
    selected, sides = [], []
    for row in manifest.rows:
        name = row.get("split", "")
        if name in training or name in testing:
            selected.append(dict(row))
            sides.append("train" if name in training else "test")
    sufficient = "train" in sides and "test" in sides
    unassigned = sum(not r.get("split") for r in manifest.rows)
    duplicate_counts = Counter(membership_key(r) for r in manifest.rows)
    duplicates = [{"key": list(key), "n_records": count} for key, count in sorted(duplicate_counts.items()) if count > 1]
    membership = _cross_overlaps(selected, sides, membership_key)
    groups = _cross_overlaps(selected, sides, group_key)
    declared = _cross_overlaps(selected, sides, lambda r: r.get("sha256") or None)
    kinds: dict[tuple, set[str]] = defaultdict(set)
    for row in manifest.rows:
        key = group_key(row)
        if key is not None:
            kinds[key].add(row.get("group_kind", "unknown"))
    contradictions = [{"key": list(k), "group_kinds": sorted(v)} for k, v in sorted(kinds.items()) if len(v) > 1]
    all_groups = sufficient and all(group_key(r) is not None and r.get("group_kind", "unknown") != "unknown" for r in selected)
    all_declared = sufficient and all(r.get("sha256") for r in selected)
    digest_labels = defaultdict(lambda: defaultdict(list))
    for row in manifest.rows:
        if row.get("sha256") and row.get("label"):
            digest_labels[row["sha256"]][row["label"]].append(list(membership_key(row)))
    label_conflicts = [{"sha256": digest, "labels_and_members": dict(sorted(labels.items()))}
                      for digest, labels in sorted(digest_labels.items()) if len(labels) > 1]
    labels_complete = all(row.get("sha256") and row.get("label") for row in manifest.rows)
    raw_findings, file_errors, hash_mismatches = [], [], []
    raw_complete = False
    if verify_files:
        if data_root is None:
            raise AuditInputError("Raw-file verification requires an explicit data_root.")
        root = Path(data_root).resolve()
        if not root.is_dir():
            raise AuditInputError("data_root must be an existing directory.")
        computed_rows = []
        for row in selected:
            key = list(membership_key(row))
            value = row.get("path", "")
            if not value:
                file_errors.append({"key": key, "reason": "missing_path"})
                continue
            candidate = Path(value)
            if candidate.is_absolute():
                file_errors.append({"key": key, "reason": "path_must_be_relative_to_data_root"})
                continue
            target = (root / candidate).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                file_errors.append({"key": key, "reason": "path_escapes_data_root"})
                continue
            try:
                digest = hashlib.sha256()
                with target.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                computed = digest.hexdigest()
            except OSError as error:
                file_errors.append({"key": key, "reason": "file_unreadable", "error_type": type(error).__name__})
                continue
            if row.get("sha256") and row["sha256"] != computed:
                hash_mismatches.append({"key": key, "provided_sha256": row["sha256"], "computed_sha256": computed})
            clone = dict(row)
            clone["computed_sha256"] = computed
            computed_rows.append((clone, "train" if row.get("split") in training else "test"))
        raw_findings = _cross_overlaps([r for r, _ in computed_rows], [s for _, s in computed_rows], lambda r: r["computed_sha256"])
        raw_complete = sufficient and len(computed_rows) == len(selected)
    checks = {
        "membership": {"status": _status(bool(membership or duplicates), sufficient and not unassigned),
                       "basis": "provided_collection_and_sample_identifiers", "cross_split_overlaps": membership,
                       "duplicate_records": duplicates},
        "groups": {"status": _status(bool(contradictions or (groups and group_policy == "disjoint")),
                                     all_groups and not unassigned and group_policy != "unspecified"),
                   "basis": "provided_namespace_and_group_identifiers", "cross_split_overlaps": groups,
                   "protocol": group_policy,
                   "overlap_detection": "DETECTED" if groups else ("NONE_DETECTED" if all_groups else "UNKNOWN"),
                   "contradictory_group_kinds": contradictions,
                   "n_missing_selected": sum(group_key(r) is None for r in selected)},
        "provided_hashes": {"status": _status(bool(declared), all_declared and not unassigned),
                            "basis": "provided_unverified_sha256_strings", "cross_split_overlaps": declared,
                            "n_missing_selected": sum(not r.get("sha256") for r in selected)},
        "label_consistency": {"status": _status(bool(label_conflicts), labels_complete),
                              "basis": "provided_unverified_sha256_strings_and_labels",
                              "conflicting_provided_labels": label_conflicts,
                              "limitation": "Consistency of labels for the same declared digest does not verify label truth."},
        "raw_content": {"status": _status(bool(raw_findings or hash_mismatches), raw_complete and not unassigned),
                        "basis": "computed_sha256_of_accessible_raw_files" if verify_files else "not_computed",
                        "cross_split_overlaps": raw_findings, "provided_hash_mismatches": hash_mismatches,
                        "file_errors": file_errors},
    }
    if lineage is not None:
        checks["declared_lineage"] = audit_lineage(manifest, lineage, train_splits=training,
                                                  validation_splits=validation, test_splits=testing)
    else:
        checks["declared_lineage"] = {"status": "UNKNOWN", "basis": "no_fit_or_model_selection_lineage_provided"}
    statuses = [check["status"] for check in checks.values()]
    aggregate = "FAIL" if "FAIL" in statuses else ("PASS" if all(s == "PASS" for s in statuses) else "UNKNOWN")
    return {"schema_version": "1.0", "audit": "integrity", "status": aggregate,
            "n_rows": len(manifest), "n_selected": len(selected), "n_train": sides.count("train"),
            "n_test": sides.count("test"), "n_unassigned_split": unassigned,
            "train_splits": sorted(training), "test_splits": sorted(testing), "validation_splits": sorted(validation), "checks": checks,
            "identity_evidence": {"status": "UNKNOWN", "basis": "metadata_only",
                                  "group_kind_counts": dict(sorted(Counter(r.get("group_kind", "unknown") for r in selected).items()))},
            "execution_leakage": {"status": "UNKNOWN", "basis": "actual_training_execution_and_historical_target_peeking_are_not_observed"},
            "limitations": ["Episode IDs are acquisition proxies, not plant, leaf, patient, or object identities.",
                            "Identity group labels are supplied metadata; their truth is not independently verified.",
                            "Different collection-local group IDs do not prove biological independence.",
                            "Hash checks identify exact byte content only; perceptual near-duplicates are not tested.",
                            "Group overlap violates a disjoint protocol; it can be appropriate for known-object/new-view evaluation.",
                            "PASS describes listed computational checks; it does not certify all forms of leakage."]}


def audit_lineage(manifest: Manifest, lineage: dict[str, Any], *, train_splits: Iterable[str] = ("train",),
                  validation_splits: Iterable[str] = ("validation", "val"),
                  test_splits: Iterable[str] = ("test",)) -> dict[str, Any]:
    """Check explicit, declared membership used by fit/model-selection stages.

    A stage declaration is not a runtime trace and does not certify execution.
    Members are objects with collection_id and sample_id, never ambiguous
    concatenated strings. Transform-only target access requires uses_labels=false.
    """
    if not isinstance(lineage, dict):
        raise AuditInputError("Lineage must be a JSON object.")
    training = _split_names(train_splits, "train_splits")
    validation = _split_names(validation_splits, "validation_splits", empty_allowed=True)
    testing = _split_names(test_splits, "test_splits")
    if training.intersection(testing) or validation.intersection(training | testing):
        raise AuditInputError("Training, validation, and held-out split names must be disjoint.")
    allowed = lineage.get("allowed_source_collections")
    stages = lineage.get("stages")
    if not isinstance(allowed, list) or not allowed or any(not isinstance(v, str) or not v for v in allowed):
        raise AuditInputError("Lineage needs a nonempty allowed_source_collections string list.")
    if not isinstance(stages, list) or not stages:
        raise AuditInputError("Lineage needs a nonempty stages list.")
    known: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in manifest.rows:
        known[membership_key(row)].append(row)
    findings, missing, stage_reports = [], [], []
    valid_purposes = {"fit", "model_selection", "calibration", "threshold", "transform"}
    names = set()
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise AuditInputError(f"Lineage stage {index}: expected an object.")
        name, purpose = stage.get("name"), stage.get("purpose")
        if not isinstance(name, str) or not name or name in names:
            raise AuditInputError("Lineage stage names must be nonempty and unique.")
        names.add(name)
        if not isinstance(purpose, str) or purpose not in valid_purposes:
            raise AuditInputError(f"Lineage stage {name}: invalid purpose.")
        field = "sample_ids" if purpose == "transform" else "fit_sample_ids"
        members = stage.get(field)
        if not isinstance(members, list) or not members:
            missing.append({"stage": name, "reason": f"missing_or_empty_{field}"})
            stage_reports.append({"name": name, "purpose": purpose, "status": "UNKNOWN", "n_members": 0})
            continue
        stage_failures, stage_unknown = 0, 0
        seen = set()
        for member in members:
            if not isinstance(member, dict) or not all(isinstance(member.get(k), str) and member[k] for k in ("collection_id", "sample_id")):
                raise AuditInputError(f"Lineage stage {name}: members need string collection_id and sample_id.")
            key = member["collection_id"], member["sample_id"]
            if key in seen:
                raise AuditInputError(f"Lineage stage {name}: repeated member {key}.")
            seen.add(key)
            records = known.get(key, [])
            reasons = []
            if not records:
                reasons.append("member_not_in_manifest")
            elif len(records) != 1:
                reasons.append("ambiguous_repeated_manifest_member")
            if purpose == "transform":
                labels = stage.get("uses_labels")
                if labels is not False and labels is not True:
                    missing.append({"stage": name, "key": list(key), "reason": "uses_labels_not_declared_boolean"})
                    stage_unknown += 1
                elif labels is True and (key[0] not in allowed or any(r.get("split") in testing for r in records)):
                    reasons.append("evaluation_labels_used_in_transform_stage")
            else:
                if key[0] not in allowed:
                    reasons.append("fit_or_selection_member_outside_allowed_sources")
                if len(records) == 1:
                    split = records[0].get("split", "")
                    accepted = training if purpose == "fit" else training | validation
                    if not split:
                        missing.append({"stage": name, "key": list(key), "reason": "membership_split_unknown"})
                        stage_unknown += 1
                    elif split not in accepted:
                        reasons.append("fit_or_selection_member_uses_held_out_split")
            if reasons:
                stage_failures += 1
                findings.append({"stage": name, "key": list(key), "reasons": reasons})
        stage_reports.append({"name": name, "purpose": purpose,
                              "status": _status(bool(stage_failures), not stage_unknown), "n_members": len(members)})
    return {"status": _status(bool(findings), not missing), "basis": "provided_declarations_only",
            "allowed_source_collections": sorted(set(allowed)), "stages": stage_reports,
            "train_splits": sorted(training), "validation_splits": sorted(validation), "test_splits": sorted(testing),
            "findings": findings, "missing_evidence": missing,
            "execution_verification": "UNKNOWN", "limitation": "Declarations do not prove actual execution or absence of historical target peeking."}
