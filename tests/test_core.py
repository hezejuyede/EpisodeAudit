"""Behavioral tests for input boundaries and statistical/evidence invariants."""

import csv
import hashlib
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from episodeaudit import (AuditInputError, audit_integrity, audit_lineage, build_episodes,
                          evaluate_predictions, load_manifest, manifest_from_rows, sample_indices)
from episodeaudit.cli import create_demo, main


def basic_rows():
    return [dict(sample_id="s1", collection_id="source", label="A", group_id="g1", group_kind="identity", split="train", sha256="1" * 64),
            dict(sample_id="t1", collection_id="target", label="B", group_id="g2", group_kind="identity", split="test", sha256="2" * 64)]


def source_lineage(sample="s1", collection="source"):
    return {"allowed_source_collections": ["source"], "stages": [{"name": "fit", "purpose": "fit", "fit_sample_ids": [{"collection_id": collection, "sample_id": sample}]}]}


class ManifestTests(unittest.TestCase):
    def test_empty_rejected(self):
        with self.assertRaises(AuditInputError):
            manifest_from_rows([])

    def test_missing_required_field_rejected(self):
        with self.assertRaises(AuditInputError):
            manifest_from_rows([{"sample_id": "a"}])

    def test_malformed_hash_rejected(self):
        rows = basic_rows()
        rows[0]["sha256"] = "not-a-digest"
        with self.assertRaises(AuditInputError):
            manifest_from_rows(rows)

    def test_repeated_members_are_retained_for_audit(self):
        rows = basic_rows()
        rows.append(dict(rows[0]))
        result = audit_integrity(manifest_from_rows(rows))
        self.assertEqual(result["checks"]["membership"]["status"], "FAIL")
        self.assertEqual(result["checks"]["membership"]["duplicate_records"][0]["n_records"], 2)

    def test_missing_evidence_never_passes(self):
        result = audit_integrity(manifest_from_rows([dict(sample_id="a", collection_id="c")]))
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["checks"]["raw_content"]["status"], "UNKNOWN")
        self.assertEqual(result["execution_leakage"]["status"], "UNKNOWN")

    def test_duplicate_csv_headers_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("sample_id,collection_id,sample_id\na,c,a\n", encoding="utf-8")
            with self.assertRaises(AuditInputError):
                load_manifest(path)

    def test_bad_csv_field_count_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("sample_id,collection_id\na,c,extra\n", encoding="utf-8")
            with self.assertRaises(AuditInputError):
                load_manifest(path)

    def test_string_ids_and_extra_fields_preserved(self):
        manifest = manifest_from_rows([dict(sample_id="001", collection_id=" C ", arbitrary=" x ")])
        self.assertEqual(manifest.rows[0]["sample_id"], "001")
        self.assertEqual(manifest.rows[0]["arbitrary"], "x")


class IntegrityTests(unittest.TestCase):
    def test_same_bare_group_across_collections_is_local(self):
        rows = basic_rows()
        rows[1]["group_id"] = "g1"
        result = audit_integrity(manifest_from_rows(rows), group_policy="disjoint")
        self.assertEqual(result["checks"]["groups"]["status"], "PASS")

    def test_explicit_shared_namespace_detected(self):
        rows = basic_rows()
        for row in rows:
            row.update(group_id="shared", group_namespace="session-registry")
        result = audit_integrity(manifest_from_rows(rows), group_policy="disjoint")
        self.assertEqual(result["checks"]["groups"]["status"], "FAIL")

    def test_allowed_object_reuse_avoids_false_failure(self):
        rows = basic_rows()
        for row in rows:
            row.update(group_id="object1", group_namespace="object-registry")
        manifest = manifest_from_rows(rows)
        unspecified = audit_integrity(manifest)
        allowed = audit_integrity(manifest, group_policy="overlap_allowed")
        self.assertEqual(unspecified["checks"]["groups"]["status"], "UNKNOWN")
        self.assertEqual(allowed["checks"]["groups"]["status"], "PASS")
        self.assertEqual(allowed["checks"]["groups"]["overlap_detection"], "DETECTED")

    def test_kind_relabel_does_not_evade_overlap(self):
        rows = basic_rows()
        for row in rows:
            row.update(group_id="same", group_namespace="global")
        rows[1]["group_kind"] = "episode"
        result = audit_integrity(manifest_from_rows(rows), group_policy="overlap_allowed")
        self.assertEqual(result["checks"]["groups"]["status"], "FAIL")

    def test_missing_group_kind_is_unknown(self):
        rows = basic_rows()
        rows[0].pop("group_kind")
        result = audit_integrity(manifest_from_rows(rows), group_policy="disjoint")
        self.assertEqual(result["checks"]["groups"]["status"], "UNKNOWN")

    def test_supplied_hash_is_not_raw_verification(self):
        result = audit_integrity(manifest_from_rows(basic_rows()), group_policy="disjoint")
        self.assertEqual(result["checks"]["provided_hashes"]["status"], "PASS")
        self.assertEqual(result["checks"]["raw_content"]["status"], "UNKNOWN")

    def test_same_split_label_conflict(self):
        rows = basic_rows()
        rows[1].update(split="train", sha256=rows[0]["sha256"])
        result = audit_integrity(manifest_from_rows(rows))
        self.assertEqual(result["checks"]["label_consistency"]["status"], "FAIL")

    def test_raw_duplicate_and_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "a.bin").write_bytes(b"same content")
            (base / "b.bin").write_bytes(b"same content")
            rows = basic_rows()
            rows[0]["path"], rows[1]["path"] = "a.bin", "b.bin"
            result = audit_integrity(manifest_from_rows(rows), verify_files=True, data_root=base)
            raw = result["checks"]["raw_content"]
            self.assertEqual(raw["status"], "FAIL")
            self.assertEqual(len(raw["cross_split_overlaps"]), 1)
            self.assertEqual(len(raw["provided_hash_mismatches"]), 2)

    def test_path_escape_is_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = basic_rows()
            rows[0]["path"] = "../outside.bin"
            result = audit_integrity(manifest_from_rows(rows), verify_files=True, data_root=directory)
            reasons = {x["reason"] for x in result["checks"]["raw_content"]["file_errors"]}
            self.assertIn("path_escapes_data_root", reasons)
            self.assertEqual(result["checks"]["raw_content"]["status"], "UNKNOWN")

    def test_target_fit_declared_failure(self):
        result = audit_lineage(manifest_from_rows(basic_rows()), source_lineage("t1", "target"))
        self.assertEqual(result["status"], "FAIL")

    def test_source_test_not_permitted_for_fit(self):
        rows = basic_rows()
        rows[0]["split"] = "test"
        result = audit_lineage(manifest_from_rows(rows), source_lineage())
        self.assertEqual(result["status"], "FAIL")

    def test_custom_split_contract_propagates(self):
        rows = basic_rows()
        rows[0]["split"], rows[1]["split"] = "learning", "future"
        result = audit_integrity(manifest_from_rows(rows), lineage=source_lineage(),
                                 train_splits=("learning",), test_splits=("future",), validation_splits=("tuning",))
        self.assertEqual(result["checks"]["declared_lineage"]["status"], "PASS")
        self.assertEqual(result["execution_leakage"]["status"], "UNKNOWN")

    def test_unknown_stage_structure_rejected(self):
        bad = {"allowed_source_collections": ["source"], "stages": [{"name": "bad", "purpose": []}]}
        with self.assertRaises(AuditInputError):
            audit_lineage(manifest_from_rows(basic_rows()), bad)


class EpisodeTests(unittest.TestCase):
    def captures(self):
        return [dict(sample_id=str(i), collection_id="c", acquisition_id="session", timestamp=stamp)
                for i, stamp in enumerate(("2026-10-01T10:00:00+00:00", "2026-10-01T10:00:05+00:00", "2026-10-01T10:00:10+00:00", "2026-10-01T10:00:16+00:00"))]

    def test_threshold_and_adjacent_chaining(self):
        result = build_episodes(manifest_from_rows(self.captures()), gap_seconds=5)
        ids = [r["group_id"] for r in result.rows]
        self.assertEqual(ids[0], ids[2])
        self.assertNotEqual(ids[2], ids[3])
        self.assertTrue(all(r["group_kind"] == "episode" for r in result.rows))

    def test_row_reordering_does_not_change_episode_assignment(self):
        rows = self.captures()
        first = build_episodes(manifest_from_rows(rows))
        second = build_episodes(manifest_from_rows(list(reversed(rows))))
        self.assertEqual({r["sample_id"]: r["group_id"] for r in first.rows}, {r["sample_id"]: r["group_id"] for r in second.rows})

    def test_day_boundary_splits(self):
        rows = self.captures()[:2]
        rows[0]["timestamp"], rows[1]["timestamp"] = "2026-10-01T23:59:59+00:00", "2026-10-02T00:00:00+00:00"
        result = build_episodes(manifest_from_rows(rows), gap_seconds=5)
        self.assertNotEqual(result.rows[0]["group_id"], result.rows[1]["group_id"])

    def test_naive_time_rejected_without_assumption(self):
        rows = self.captures()
        rows[0]["timestamp"] = "2026-10-01T10:00:00"
        with self.assertRaises(AuditInputError):
            build_episodes(manifest_from_rows(rows))
        result = build_episodes(manifest_from_rows(rows), naive_timezone="UTC")
        self.assertEqual(result.rows[0]["episode_time_basis"], "assumed_timezone:UTC")

    def test_missing_acquisition_key_rejected(self):
        rows = self.captures()
        rows[0].pop("acquisition_id")
        with self.assertRaises(AuditInputError):
            build_episodes(manifest_from_rows(rows))


class SamplingTests(unittest.TestCase):
    def groups(self):
        return manifest_from_rows([dict(sample_id=f"{group}-{i}", collection_id="c", group_id=str(group), group_kind="episode", split="train")
                                   for group, count in enumerate((1, 2, 4, 8)) for i in range(count)])

    def test_zero_draw_groups_counted(self):
        result = sample_indices(self.groups(), 1, strategy="episode", seed=17)
        self.assertEqual(len(result["group_exposures"]), 4)
        self.assertEqual(sum(r["n_draws"] == 0 for r in result["group_exposures"]), 3)
        self.assertAlmostEqual(result["draw_count_cv"], math.sqrt(3), places=12)

    def test_equal_budget_and_determinism(self):
        manifest = self.groups()
        a = sample_indices(manifest, 10, strategy="episode", seed=23)
        b = sample_indices(manifest, 10, strategy="episode", seed=23)
        c = sample_indices(manifest, 10, strategy="image", seed=23)
        self.assertEqual(a, b)
        self.assertEqual(len(a["indices"]), len(c["indices"]))
        self.assertEqual(len(set(c["indices"])), 10)

    def test_image_expected_exposure_is_size_weighted(self):
        result = sample_indices(self.groups(), 15, strategy="image", seed=0)
        self.assertEqual([r["expected_draws"] for r in result["expected_group_exposures"]], [1, 2, 4, 8])
        self.assertEqual([r["n_draws"] for r in result["group_exposures"]], [1, 2, 4, 8])

    def test_zero_budget_cv_undefined(self):
        result = sample_indices(self.groups(), 0, strategy="episode")
        self.assertIsNone(result["draw_count_cv"])
        self.assertEqual(result["groups_seen"], 0)

    def test_missing_group_cannot_balance(self):
        manifest = manifest_from_rows([dict(sample_id="a", collection_id="c")])
        with self.assertRaises(AuditInputError):
            sample_indices(manifest, 1, strategy="group")
        self.assertEqual(sample_indices(manifest, 1)["group_evidence_status"], "UNKNOWN")

    def test_episode_kind_required(self):
        manifest = manifest_from_rows(basic_rows())
        with self.assertRaises(AuditInputError):
            sample_indices(manifest, 1, strategy="episode")
        self.assertEqual(len(sample_indices(manifest, 1, strategy="group")["indices"]), 1)


class MetricTests(unittest.TestCase):
    def examples(self):
        manifest = manifest_from_rows([dict(sample_id=str(i), collection_id="c", label=label, group_id=f"g{i // 2}", group_kind="identity") for i, label in enumerate(("A", "A", "B", "B"))])
        predictions = [dict(sample_id=str(i), collection_id="c", y_true=actual, y_pred=estimate)
                       for i, (actual, estimate) in enumerate(zip(("A", "A", "B", "B"), ("A", "B", "B", "B")))]
        return manifest, predictions

    def test_known_metrics_and_absent_class(self):
        manifest, predictions = self.examples()
        result = evaluate_predictions(predictions, manifest=manifest, classes=("A", "B", "C"))
        self.assertEqual(result["metrics"]["balanced_accuracy"], .75)
        self.assertEqual(result["metrics"]["accuracy"], .75)
        self.assertIsNone(result["metrics"]["per_class"][2]["recall"])
        self.assertEqual(result["probability_evidence"]["status"], "UNKNOWN")

    def test_manifest_label_mismatch_rejected(self):
        manifest, predictions = self.examples()
        predictions[0]["y_true"] = "B"
        with self.assertRaises(AuditInputError):
            evaluate_predictions(predictions, manifest=manifest)

    def test_orphan_member_rejected(self):
        manifest, predictions = self.examples()
        predictions[0]["sample_id"] = "orphan"
        with self.assertRaises(AuditInputError):
            evaluate_predictions(predictions, manifest=manifest)

    def test_repeated_predictions_rejected(self):
        _, predictions = self.examples()
        with self.assertRaises(AuditInputError):
            evaluate_predictions(predictions + [predictions[0]])

    def test_bootstrap_units_and_determinism(self):
        manifest, predictions = self.examples()
        a = evaluate_predictions(predictions, manifest=manifest, bootstrap=100, unit="group", seed=8, stratify=True)
        b = evaluate_predictions(predictions, manifest=manifest, bootstrap=100, unit="group", seed=8, stratify=True)
        self.assertEqual(a, b)
        self.assertEqual(a["bootstrap"]["n_units"], 2)
        self.assertEqual(a["bootstrap"]["n_replicates_missing_original_truth_classes"], 0)

    def test_group_bootstrap_does_not_fallback_to_images(self):
        _, predictions = self.examples()
        with self.assertRaises(AuditInputError):
            evaluate_predictions(predictions, bootstrap=20, unit="group")

    def test_probability_mapping_validation(self):
        _, predictions = self.examples()
        for row in predictions:
            row.update(pA=.6 if row["y_pred"] == "A" else .4, pB=.4 if row["y_pred"] == "A" else .6)
        result = evaluate_predictions(predictions, probability_columns={"A": "pA", "B": "pB"}, decision_rule="argmax")
        self.assertEqual(result["probability_evidence"]["status"], "PASS")
        self.assertEqual(result["probability_evidence"]["calibration"], "not_assessed")
        predictions[0]["pA"] = float("nan")
        with self.assertRaises(AuditInputError):
            evaluate_predictions(predictions, probability_columns={"A": "pA", "B": "pB"})

    def test_declared_argmax_violation_rejected(self):
        _, predictions = self.examples()
        for row in predictions:
            row.update(pA=.5, pB=.5)
        # Tied maxima are valid under argmax without an arbitrary tie-break.
        evaluate_predictions(predictions, probability_columns={"A": "pA", "B": "pB"}, decision_rule="argmax")
        predictions[0].update(pA=.1, pB=.9)
        with self.assertRaises(AuditInputError):
            evaluate_predictions(predictions, probability_columns={"A": "pA", "B": "pB"}, decision_rule="argmax")


class CLITests(unittest.TestCase):
    def test_demo_and_error_json(self):
        with tempfile.TemporaryDirectory() as directory:
            result = create_demo(directory)
            self.assertEqual(result["data_kind"], "synthetic_software_test_only")
            self.assertEqual(result["integrity_status"], "PASS")
            output = Path(directory) / "bad.json"
            code = main(["sample", str(Path(directory) / "manifest.csv"), "--n-draws", "-1", "--output", str(output)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "ERROR")

    def test_require_pass_unknown_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            create_demo(directory)
            output = Path(directory) / "unknown.json"
            code = main(["audit", str(Path(directory) / "manifest.csv"), "--require-pass", "--output", str(output)])
            self.assertEqual(code, 3)

    def test_unwritable_output_produces_json_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            create_demo(directory)
            capture = io.StringIO()
            with redirect_stdout(capture):
                code = main(["audit", str(Path(directory) / "manifest.csv"), "--output", str(Path(directory) / "missing-parent" / "report.json")])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(capture.getvalue())["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
