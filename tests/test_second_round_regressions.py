"""Regression controls discovered after the first frozen validation run.

These tests are not represented as preregistered scientific validation.
"""
import unittest

from episodeaudit import (AuditInputError, audit_integrity, audit_lineage, build_episodes,
                          evaluate_predictions, manifest_from_rows, sample_indices)


def row(sample, collection="source", **metadata):
    return {"sample_id": sample, "collection_id": collection, **metadata}


def transform_lineage(uses_labels=True):
    return {"allowed_source_collections": ["source"], "stages": [{
        "name": "transform", "purpose": "transform", "uses_labels": uses_labels,
        "sample_ids": [{"collection_id": "source", "sample_id": "a"}]}]}


def predictions(manifest):
    return [{"sample_id": r["sample_id"], "collection_id": r["collection_id"],
             "y_true": r["label"], "y_pred": r["label"]} for r in manifest.rows]


class LineageRegressionTests(unittest.TestCase):
    def test_label_using_transform_cannot_pass_missing_or_unknown_partition(self):
        for split in ("", "future", "training-typo"):
            with self.subTest(split=split):
                result = audit_lineage(manifest_from_rows([row("a", split=split)]), transform_lineage())
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(result["stages"][0]["status"], "UNKNOWN")
                self.assertTrue(result["missing_evidence"])

    def test_label_using_transform_train_validation_and_test_controls(self):
        for split, expected in (("train", "PASS"), ("validation", "PASS"), ("val", "PASS"), ("test", "FAIL")):
            with self.subTest(split=split):
                result = audit_lineage(manifest_from_rows([row("a", split=split)]), transform_lineage())
                self.assertEqual(result["status"], expected)

    def test_target_label_use_fails_but_label_free_inference_is_permitted(self):
        declaration = transform_lineage()
        declaration["stages"][0]["sample_ids"][0]["collection_id"] = "target"
        manifest = manifest_from_rows([row("a", "target", split="test")])
        self.assertEqual(audit_lineage(manifest, declaration)["status"], "FAIL")
        declaration["stages"][0]["uses_labels"] = False
        self.assertEqual(audit_lineage(manifest, declaration)["status"], "PASS")

    def test_custom_partition_names_control(self):
        for split, expected in (("learning", "PASS"), ("tuning", "PASS"), ("future", "FAIL"), ("train", "UNKNOWN")):
            with self.subTest(split=split):
                result = audit_lineage(manifest_from_rows([row("a", split=split)]), transform_lineage(),
                                       train_splits=("learning",), validation_splits=("tuning",), test_splits=("future",))
                self.assertEqual(result["status"], expected)


class GroupConsistencyRegressionTests(unittest.TestCase):
    def test_conflicts_rejected_by_each_group_consumer(self):
        for other_kind in ("episode", "other", "unknown"):
            with self.subTest(other_kind=other_kind):
                manifest = manifest_from_rows([row("a", label="A", group_id="1", group_namespace="global", group_kind="identity"),
                                               row("b", label="A", group_id="1", group_namespace="global", group_kind=other_kind),
                                               row("c", label="B", group_id="2", group_kind="identity")])
                self.assertEqual(audit_integrity(manifest)["checks"]["groups"]["status"], "FAIL")
                with self.assertRaises(AuditInputError):
                    sample_indices(manifest, 5, strategy="group")
                with self.assertRaises(AuditInputError):
                    evaluate_predictions(predictions(manifest), manifest=manifest, bootstrap=10, unit="group")

    def test_all_unknown_kind_groups_resample_but_evidence_is_unknown(self):
        manifest = manifest_from_rows([row("a", label="A", group_id="1"), row("b", label="B", group_id="2")])
        sample = sample_indices(manifest, 4, strategy="group")
        metrics = evaluate_predictions(predictions(manifest), manifest=manifest, bootstrap=10, unit="group")
        self.assertEqual(sample["group_evidence_status"], "UNKNOWN")
        self.assertEqual(metrics["group_evidence_status"], "UNKNOWN")
        self.assertEqual(metrics["bootstrap"]["n_units"], 2)
        self.assertIn("unknown", metrics["bootstrap"]["inference_boundary"])

    def test_same_bare_group_with_different_collection_namespaces_is_valid(self):
        manifest = manifest_from_rows([row("a", "A", label="A", group_id="1", group_kind="identity"),
                                       row("a", "B", label="B", group_id="1", group_kind="episode")])
        self.assertEqual(sample_indices(manifest, 4, strategy="group")["n_groups"], 2)
        result = evaluate_predictions(predictions(manifest), manifest=manifest)
        self.assertEqual(result["group_evidence_status"], "PASS")
        self.assertEqual(result["n_provided_groups"], 2)

    def test_sampling_only_validates_selected_rows(self):
        manifest = manifest_from_rows([row("a", label="A", group_id="1", group_kind="identity", split="train"),
                                       row("b", label="A", group_id="1", group_kind="episode", split="test")])
        result = sample_indices(manifest, 1, strategy="group", splits=("train",))
        self.assertEqual(result["group_evidence_status"], "PASS")


class NonfiniteScalarRegressionTests(unittest.TestCase):
    def test_nonfinite_manifest_scalar_cannot_become_id_or_metadata(self):
        for field in ("sample_id", "collection_id", "label", "group_id", "arbitrary"):
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(field=field, value=value):
                    data = row("a", label="A", group_id="1")
                    data[field] = value
                    with self.assertRaises(AuditInputError):
                        manifest_from_rows([data])

    def test_nonfinite_prediction_scalar_cannot_become_truth_or_id(self):
        for field in ("sample_id", "collection_id", "y_true", "y_pred"):
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(field=field, value=value):
                    data = {"sample_id": "a", "collection_id": "c", "y_true": "A", "y_pred": "A", field: value}
                    with self.assertRaises(AuditInputError):
                        evaluate_predictions([data])

    def test_literal_nan_strings_and_optional_none_are_not_guessed(self):
        manifest = manifest_from_rows([row("nan", label="nan", group_id="nan", group_kind="identity", arbitrary=None)])
        self.assertEqual(manifest.rows[0]["sample_id"], "nan")
        self.assertEqual(manifest.rows[0]["arbitrary"], "")
        self.assertEqual(evaluate_predictions(predictions(manifest), manifest=manifest)["metrics"]["accuracy"], 1.0)


class EpisodePermissionRegressionTests(unittest.TestCase):
    def test_only_boolean_true_authorizes_overwrite(self):
        manifest = manifest_from_rows([row("a", group_id="original", group_kind="identity",
                                           timestamp="2026-01-01T00:00:00+00:00", acquisition_id="camera")])
        for value in ("False", "True", 0, 1, None):
            with self.subTest(value=value):
                with self.assertRaises(AuditInputError):
                    build_episodes(manifest, overwrite_groups=value)
        with self.assertRaises(AuditInputError):
            build_episodes(manifest, overwrite_groups=False)
        result = build_episodes(manifest, overwrite_groups=True)
        self.assertEqual(result.rows[0]["group_kind"], "episode")
        self.assertEqual(manifest.rows[0]["group_id"], "original")


if __name__ == "__main__":
    unittest.main()
