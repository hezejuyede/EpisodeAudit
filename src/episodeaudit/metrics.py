"""Class-conditional reports and explicit resampling units for predictions."""

from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from .manifest import AuditInputError, Manifest, group_key, membership_key


def load_predictions(path: str | Path) -> list[dict[str, str]]:
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            names = reader.fieldnames
            if names is None or len(names) != len(set(names)) or not {"sample_id", "y_true", "y_pred"}.issubset(names):
                raise AuditInputError("Predictions require unique sample_id, y_true, and y_pred column names.")
            rows = []
            for line, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise AuditInputError(f"Prediction row {line}: malformed CSV field count.")
                rows.append(row)
        return rows
    except (OSError, UnicodeError, csv.Error) as error:
        raise AuditInputError(f"Unable to read prediction CSV: {error}") from error


def _statistics(truth: np.ndarray, predicted: np.ndarray, classes: list[str]) -> dict[str, Any]:
    positions = {label: index for index, label in enumerate(classes)}
    confusion = np.zeros((len(classes), len(classes)), dtype=np.int64)
    for actual, estimate in zip(truth, predicted):
        confusion[positions[str(actual)], positions[str(estimate)]] += 1
    support, assigned = confusion.sum(axis=1), confusion.sum(axis=0)
    hits = np.diag(confusion)
    recalls = [float(hit / count) if count else None for hit, count in zip(hits, support)]
    precisions = [float(hit / count) if count else None for hit, count in zip(hits, assigned)]
    f1 = [float(2 * hit / (n_true + n_pred)) if n_true + n_pred else None
          for hit, n_true, n_pred in zip(hits, support, assigned)]
    observed = [i for i, count in enumerate(support) if count]
    # Predictions into absent truth classes contribute false negatives to
    # observed classes; absent truth recalls are explicitly undefined.
    ba = float(np.mean([recalls[i] for i in observed])) if observed else None
    macro_f1 = float(np.mean([f1[i] for i in observed])) if observed else None
    return {"n_predictions": int(len(truth)), "accuracy": float(hits.sum() / len(truth)) if len(truth) else None,
            "balanced_accuracy": ba, "macro_f1_observed_truth_classes": macro_f1,
            "classes": classes, "confusion_matrix": confusion.tolist(),
            "observed_truth_classes": [classes[i] for i in observed],
            "per_class": [{"label": label, "n_true": int(support[i]), "n_predicted": int(assigned[i]),
                           "n_correct": int(hits[i]), "recall": recalls[i], "precision": precisions[i], "f1": f1[i]}
                          for i, label in enumerate(classes)],
            "balanced_accuracy_definition": "Mean recall over classes present in y_true; absent-class recalls are undefined."}


def evaluate_predictions(predictions: Iterable[Mapping[str, object]], *, manifest: Manifest | None = None,
                         classes: Iterable[str] | None = None, bootstrap: int = 0, seed: int = 0,
                         unit: str = "image", confidence: float = 0.95,
                         stratify: bool = False, probability_columns: Mapping[str, str] | None = None,
                         decision_rule: str | None = None) -> dict[str, Any]:
    """Evaluate fixed predictions; this function does not train or select models.

    Group bootstrap resamples explicitly supplied group keys with replacement,
    retaining all rows from each drawn group. Labels and identities are not
    independently validated. Image bootstrap is conditional on individual rows
    and cannot establish independent-specimen or external-collection uncertainty.
    """
    if isinstance(bootstrap, bool) or not isinstance(bootstrap, (int, np.integer)) or bootstrap < 0:
        raise AuditInputError("bootstrap must be a nonnegative integer.")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise AuditInputError("seed must be a nonnegative integer.")
    if unit not in {"image", "group"}:
        raise AuditInputError("bootstrap unit must be image or group.")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 < confidence < 1:
        raise AuditInputError("confidence must be strictly between zero and one.")
    if not isinstance(stratify, bool):
        raise AuditInputError("stratify must be boolean.")
    if decision_rule is not None and decision_rule != "argmax":
        raise AuditInputError("decision_rule must be None or argmax.")
    if probability_columns is not None:
        if not isinstance(probability_columns, Mapping) or not probability_columns or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in probability_columns.items()):
            raise AuditInputError("probability_columns must map nonempty class labels to column names.")
        if len(set(probability_columns.values())) != len(probability_columns):
            raise AuditInputError("Probability column names must be distinct.")
    rows, originals = [], []
    for index, item in enumerate(predictions, 2):
        if not isinstance(item, Mapping):
            raise AuditInputError(f"Prediction row {index}: expected a mapping.")
        row = {}
        for field in ("sample_id", "collection_id", "y_true", "y_pred"):
            value = item.get(field, "")
            if value is None:
                value = ""
            if not isinstance(value, (str, int, float)):
                raise AuditInputError(f"Prediction row {index}: {field} must be scalar.")
            row[field] = str(value).strip()
        if any(not row[field] for field in ("sample_id", "y_true", "y_pred")):
            raise AuditInputError(f"Prediction row {index}: sample_id, y_true, and y_pred must be nonempty.")
        rows.append(row)
        originals.append(item)
    if not rows:
        raise AuditInputError("Predictions have no rows.")
    manifest_lookup, by_sample = defaultdict(list), defaultdict(list)
    if manifest is not None:
        for row in manifest.rows:
            manifest_lookup[membership_key(row)].append(row)
            by_sample[row["sample_id"]].append(row)
    linked = []
    membership = []
    for row in rows:
        if manifest is not None:
            candidates = manifest_lookup[(row["collection_id"], row["sample_id"])] if row["collection_id"] else by_sample[row["sample_id"]]
            if len(candidates) != 1:
                raise AuditInputError("Every prediction must resolve to exactly one manifest member; provide collection_id when necessary.")
            member = candidates[0]
            if member.get("label") and member["label"] != row["y_true"]:
                raise AuditInputError("Prediction y_true disagrees with the supplied manifest label.")
            linked.append(member)
            membership.append(membership_key(member))
        else:
            linked.append(None)
            membership.append((row["collection_id"], row["sample_id"]))
    if len(membership) != len(set(membership)):
        raise AuditInputError("Repeated predictions for a membership key require a separate declared analysis, not silent pooling.")
    actual = np.asarray([row["y_true"] for row in rows])
    estimated = np.asarray([row["y_pred"] for row in rows])
    observed_labels = set(actual.tolist()).union(estimated.tolist())
    if classes is None:
        ordered_classes = sorted(probability_columns) if probability_columns is not None else sorted(observed_labels)
        if not observed_labels.issubset(ordered_classes):
            raise AuditInputError("A true or predicted label is absent from the probability class mapping.")
    else:
        ordered_classes = list(classes)
        if not ordered_classes or len(set(ordered_classes)) != len(ordered_classes) or any(not isinstance(v, str) or not v for v in ordered_classes):
            raise AuditInputError("classes must be a nonempty sequence of unique string labels.")
        if not observed_labels.issubset(ordered_classes):
            raise AuditInputError("A true or predicted label is absent from the declared class list.")
    probability_report = {"status": "UNKNOWN", "basis": "no_explicit_probability_class_mapping",
                          "decision_rule_verification": "UNKNOWN", "calibration": "not_assessed"}
    if probability_columns is not None:
        if set(probability_columns) != set(ordered_classes):
            raise AuditInputError("Probability mapping must represent exactly the declared class set.")
        matrix = []
        for index, item in enumerate(originals, 2):
            values = []
            for label in ordered_classes:
                column = probability_columns[label]
                try:
                    value = float(item[column])
                except (KeyError, TypeError, ValueError, OverflowError) as error:
                    raise AuditInputError(f"Prediction row {index}: missing or nonnumeric probability for {label}.") from error
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise AuditInputError(f"Prediction row {index}: probabilities must be finite and within [0,1].")
                values.append(value)
            if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-6):
                raise AuditInputError(f"Prediction row {index}: probabilities must sum to one within 1e-6.")
            if decision_rule == "argmax":
                predicted_index = ordered_classes.index(rows[index - 2]["y_pred"])
                if values[predicted_index] != max(values):
                    raise AuditInputError(f"Prediction row {index}: y_pred violates the declared argmax decision rule.")
            matrix.append(values)
        probability_report = {"status": "PASS", "basis": "provided_numeric_probabilities_with_explicit_class_mapping",
                              "class_columns": dict(sorted(probability_columns.items())), "sum_tolerance": 1e-6,
                              "decision_rule_verification": "PASS" if decision_rule == "argmax" else "UNKNOWN",
                              "decision_rule": decision_rule, "n_validated_rows": len(matrix), "calibration": "not_assessed",
                              "limitation": "Numeric consistency does not establish calibration quality or honest probability generation."}
    elif decision_rule == "argmax":
        raise AuditInputError("Argmax verification requires an explicit probability column mapping.")
    primary = _statistics(actual, estimated, ordered_classes)
    group_members: dict[tuple, list[int]] = {}
    missing_groups = 0
    for index, member in enumerate(linked):
        key = group_key(member) if member is not None else None
        if key is None:
            missing_groups += 1
        else:
            group_members.setdefault(key, []).append(index)
    group_reports = []
    for key, positions in sorted(group_members.items()):
        stats = _statistics(actual[positions], estimated[positions], ordered_classes)
        group_reports.append({"key": list(key), "n_predictions": stats["n_predictions"],
                              "accuracy": stats["accuracy"], "balanced_accuracy": stats["balanced_accuracy"],
                              "true_label_counts": dict(sorted(Counter(actual[positions].tolist()).items()))})
    for item in primary["per_class"]:
        label = item["label"]
        item["n_provided_groups_with_true_class"] = sum(any(actual[i] == label for i in positions) for positions in group_members.values()) if not missing_groups else None
    report = {"schema_version": "1.0", "audit": "predictions", "metrics": primary,
              "group_evidence_status": "PASS" if not missing_groups else "UNKNOWN",
              "n_provided_groups": len(group_members), "n_predictions_missing_group": missing_groups,
              "group_metrics": group_reports, "probability_evidence": probability_report, "bootstrap": {"performed": False},
              "limitations": ["Predictions and labels are supplied; pathology and label truth are not verified.",
                              "Group labels do not by themselves establish specimen independence.",
                              "Confidence intervals are conditional on the recorded rows/groups and fixed model predictions.",
                              "Seeds, views, groups, specimens, and independently collected datasets are different units.",
                              "No causal collection-shift mechanism or future-domain generalization is inferred."]}
    if not bootstrap:
        return report
    if unit == "group" and missing_groups:
        raise AuditInputError("Group bootstrap requires a provided group identifier for every prediction.")
    if unit == "group":
        units = [np.asarray(v, dtype=np.int64) for _, v in sorted(group_members.items())]
        kinds = sorted({member.get("group_kind", "unknown") for member in linked if member is not None})
        boundary = "Provided " + "/".join(kinds) + " groups; group identity and independence are unverified."
    else:
        units = [np.asarray([i], dtype=np.int64) for i in range(len(rows))]
        boundary = "Individual prediction rows; biological/specimen and collection-level uncertainty is not estimated."
    if len(units) < 2:
        raise AuditInputError("At least two resampling units are required for a bootstrap interval.")
    strata: dict[str, list[int]] = {}
    if stratify:
        for index, positions in enumerate(units):
            labels = set(actual[positions].tolist())
            if len(labels) != 1:
                raise AuditInputError("Class-stratified group bootstrap requires class-homogeneous groups; mixed groups cannot be silently split.")
            strata.setdefault(next(iter(labels)), []).append(index)
    else:
        strata["all"] = list(range(len(units)))
    rng = np.random.default_rng(int(seed))
    draws = {"accuracy": [], "balanced_accuracy": [], "macro_f1_observed_truth_classes": []}
    original_truth = set(actual.tolist())
    incomplete = 0
    for _ in range(int(bootstrap)):
        selected_units = [int(i) for label in sorted(strata) for i in rng.choice(strata[label], size=len(strata[label]), replace=True)]
        positions = np.concatenate([units[i] for i in selected_units])
        statistics = _statistics(actual[positions], estimated[positions], ordered_classes)
        draws["accuracy"].append(statistics["accuracy"])
        if set(actual[positions].tolist()) != original_truth:
            incomplete += 1
            continue
        draws["balanced_accuracy"].append(statistics["balanced_accuracy"])
        draws["macro_f1_observed_truth_classes"].append(statistics["macro_f1_observed_truth_classes"])
    alpha = (1 - confidence) / 2
    intervals = {}
    for name, values in draws.items():
        if values:
            lower, upper = np.quantile(np.asarray(values), [alpha, 1 - alpha])
            intervals[name] = {"lower": float(lower), "upper": float(upper), "n_valid_replicates": len(values)}
        else:
            intervals[name] = {"lower": None, "upper": None, "n_valid_replicates": 0}
    report["bootstrap"] = {"performed": True, "unit": unit, "n_units": len(units), "n_replicates": int(bootstrap),
                           "seed": int(seed), "confidence": float(confidence), "method": "percentile",
                           "class_stratified": stratify, "intervals": intervals,
                           "n_replicates_missing_original_truth_classes": incomplete,
                           "class_metric_interval_conditioning": "Replicates retaining all originally observed truth classes; missing-class replicates are explicitly excluded.",
                           "inference_boundary": boundary,
                           "warnings": ["Some original truth classes are absent in bootstrap replicates; class-metric intervals are conditional."] if incomplete else []}
    return report
