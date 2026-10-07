"""Relative-path replay of 13 post-discovery correction/control domains.
Original failed inputs remain historical evidence; this is not preregistration.
"""
import json
from pathlib import Path
from episodeaudit import audit_integrity, audit_lineage, build_episodes, evaluate_predictions, manifest_from_rows, sample_indices

BASE = Path(__file__).resolve().parents[1]

def row(sample, collection="source", **kwargs):
    return {"sample_id": sample, "collection_id": collection, **kwargs}

def predictions(manifest):
    return [{"sample_id": r["sample_id"], "collection_id": r["collection_id"], "y_true": r["label"], "y_pred": r["label"]} for r in manifest.rows]

def caught(call):
    try:
        return {"returned": call()}
    except Exception as error:
        return {"error_type": type(error).__name__, "message": str(error)}

def main():
    checks = []
    def check(name, observed, correct):
        checks.append({"name": name, "corrected_or_control_behavior": bool(correct), "observed": observed})

    cross = manifest_from_rows([row("same", "A", label="positive", group_id="1", group_kind="identity", split="train"),
                                row("same", "B", label="negative", group_id="1", group_kind="identity", split="test")])
    audit = audit_integrity(cross, group_policy="disjoint")
    metrics = evaluate_predictions(predictions(cross), manifest=cross)
    bare = caught(lambda: evaluate_predictions([{"sample_id": "same", "y_true": "positive", "y_pred": "positive"}], manifest=cross))
    check("collection_local_id_controls", {"membership": audit["checks"]["membership"]["status"], "groups": audit["checks"]["groups"]["status"], "bare": bare},
          audit["checks"]["membership"]["status"] == audit["checks"]["groups"]["status"] == "PASS"
          and metrics["metrics"]["n_predictions"] == 2 and bare.get("error_type") == "AuditInputError")
    result = audit_integrity(manifest_from_rows([dict(r, group_namespace="global-plants") for r in cross.rows]), group_policy="disjoint")
    check("explicit_shared_namespace", result["checks"]["groups"], result["checks"]["groups"]["status"] == "FAIL")

    declaration = {"allowed_source_collections": ["source"], "stages": [{"name": "label-consuming-transform", "purpose": "transform", "uses_labels": True,
                                                                       "sample_ids": [{"sample_id": "u", "collection_id": "source"}]}]}
    for name, split, expected in (("label_transform_missing_partition", "", "UNKNOWN"),
                                  ("label_transform_unknown_partition", "future", "UNKNOWN"),
                                  ("label_transform_known_test_control", "test", "FAIL")):
        result = audit_lineage(manifest_from_rows([row("u", label="A", split=split)]), declaration)
        check(name, result, result["status"] == expected)

    contradictory = manifest_from_rows([row("a", label="A", group_id="1", group_kind="identity", group_namespace="shared"),
                                         row("b", label="A", group_id="1", group_kind="episode", group_namespace="shared"),
                                         row("c", label="B", group_id="2", group_kind="identity", group_namespace="shared")])
    metrics = caught(lambda: evaluate_predictions(predictions(contradictory), manifest=contradictory, unit="group", bootstrap=25, seed=7))
    sampling = caught(lambda: sample_indices(contradictory, 10, strategy="group", seed=7))
    check("contradictory_group_kinds_consumers", {"metrics": metrics, "sampling": sampling},
          metrics.get("error_type") == sampling.get("error_type") == "AuditInputError")
    nan_manifest = caught(lambda: manifest_from_rows([row("a", label="A", group_id=float("nan"), group_kind="identity"),
                                                     row("b", label="B", group_id=float("nan"), group_kind="identity")]))
    check("numeric_nan_group_silent_identity", nan_manifest, nan_manifest.get("error_type") == "AuditInputError")
    nan_prediction = caught(lambda: evaluate_predictions([{"sample_id": float("nan"), "y_true": float("nan"), "y_pred": float("nan")},
                                                          {"sample_id": "b", "y_true": "B", "y_pred": "B"}]))
    check("numeric_nan_prediction_silent_class", nan_prediction, nan_prediction.get("error_type") == "AuditInputError")

    mixed = manifest_from_rows([row("a", label="A", group_id="1", group_kind="identity"),
                                row("b", label="B", group_id="1", group_kind="identity"),
                                row("c", label="A", group_id="2", group_kind="identity")])
    result = caught(lambda: evaluate_predictions(predictions(mixed), manifest=mixed, bootstrap=10, unit="group", stratify=True))
    check("mixed_class_group_stratification_control", result, result.get("error_type") == "AuditInputError")
    single = manifest_from_rows([row("a", label="A", group_id="1", group_kind="identity")])
    result = caught(lambda: evaluate_predictions(predictions(single), manifest=single, bootstrap=10, unit="group"))
    zero = sample_indices(single, 0, strategy="group")
    check("single_group_and_zero_draw_control", {"bootstrap": result, "cv": zero["draw_count_cv"], "groups_seen": zero["groups_seen"]},
          result.get("error_type") == "AuditInputError" and zero["draw_count_cv"] is None and zero["groups_seen"] == 0)
    result = caught(lambda: manifest_from_rows([]))
    check("empty_manifest_control", result, result.get("error_type") == "AuditInputError")

    p = [{"sample_id": "a", "y_true": "A", "y_pred": "B", "pA": .8, "pB": .2}]
    argmax = caught(lambda: evaluate_predictions(p, probability_columns={"A": "pA", "B": "pB"}, decision_rule="argmax"))
    unspecified = evaluate_predictions(p, probability_columns={"A": "pA", "B": "pB"})
    tied = evaluate_predictions([dict(p[0], pA=.5, pB=.5)], probability_columns={"A": "pA", "B": "pB"}, decision_rule="argmax")
    check("decision_rule_controls", {"argmax": argmax, "unspecified": unspecified["probability_evidence"], "tied": tied["probability_evidence"]},
          argmax.get("error_type") == "AuditInputError" and unspecified["probability_evidence"]["decision_rule_verification"] == "UNKNOWN"
          and tied["probability_evidence"]["decision_rule_verification"] == "PASS")
    old = manifest_from_rows([row("a", group_id="old", group_kind="identity", timestamp="2026-01-01T00:00:00+00:00", acquisition_id="camera")])
    result = caught(lambda: build_episodes(old, overwrite_groups="False"))
    check("episode_overwrite_boolean_type", result, result.get("error_type") == "AuditInputError")

    result = {"n_domains": len(checks), "n_failed_domains": sum(not c["corrected_or_control_behavior"] for c in checks),
              "checks": checks, "boundary": "Post-discovery software regression replay; no biological or third-party validity claim."}
    output = BASE / "replayed_results/adversarial"
    output.mkdir(parents=True, exist_ok=True)
    (output / "RECHECK_REPORT.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"n_domains": result["n_domains"], "n_failed_domains": result["n_failed_domains"]}))
    return bool(result["n_failed_domains"])

if __name__ == "__main__":
    raise SystemExit(main())
