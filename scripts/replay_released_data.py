"""Replay released software fixtures and derived outputs using relative paths.

No models are fitted and no raw photos are downloaded by this program. The U0
input contains aggregate group counts; expanded rows are artificial bookkeeping
records representing those counts, not reconstructed images or new observations.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path

from episodeaudit import (audit_integrity, evaluate_predictions, load_manifest,
                          load_predictions, manifest_from_rows, sample_indices)

REPOSITORY = Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer=csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def hash_only_overlap(rows):
    seen=collections.defaultdict(set)
    for row in rows:
        if row.get("sha256"):
            seen[row["sha256"]].add(row.get("split"))
    return any({"train","test"} <= names for names in seen.values())


def group_only_overlap(rows):
    seen=collections.defaultdict(set)
    for row in rows:
        if row.get("group_id"):
            key=("explicit",row["group_namespace"],row["group_id"]) if row.get("group_namespace") else ("collection",row["collection_id"],row["group_id"])
            seen[key].add(row.get("split"))
    return any({"train","test"} <= names for names in seen.values())


def expand_group_counts(ledger):
    records=[]
    for group in ledger:
        count=int(group["n_records"])
        if count <= 0:
            raise ValueError("Group-size ledger must have positive counts.")
        for index in range(count):
            records.append({"sample_id":f"bookkeeping-{group['anonymous_group_id']}-{index:04d}",
                            "collection_id":"aggregate-U0-ledger", "group_id":group["anonymous_group_id"],
                            "group_namespace":"anonymous-acquisition-counts", "group_kind":"episode",
                            "split":group["split"]})
    return manifest_from_rows(records)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPOSITORY/"replayed_results")
    parser.add_argument("--coil-raw", type=Path, help="Optional separately obtained original COIL raw-image directory.")
    parser.add_argument("--bootstrap", type=int, default=2000)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    synthetic=REPOSITORY/"data/synthetic"
    derived=REPOSITORY/"data/derived"
    checks=[]
    def check(name, condition):
        checks.append({"name":name,"passed":bool(condition)})
    receipt=json.loads((synthetic/"FIXTURE_FREEZE_RECEIPT.json").read_text(encoding="utf-8"))
    outcomes=[]
    for spec in receipt["cases"]:
        path=synthetic/spec["file"]
        check("frozen_bytes:"+spec["file"],hashlib.sha256(path.read_bytes()).hexdigest()==spec["sha256"])
        manifest=load_manifest(path)
        report=audit_integrity(manifest, group_policy="disjoint")
        observed={key:value["status"] for key,value in report["checks"].items()}
        matched=all(observed.get(key)==value for key,value in spec["expected_checks"].items())
        check("known_truth:"+spec["file"],matched)
        outcomes.append({"seed":spec["seed"],"family":spec["family"],"n_rows":len(manifest),"oracle_match":matched,
                         "episodeaudit_observed_violation":any(value=="FAIL" for value in observed.values()),
                         "hash_only_observed_cross_split":hash_only_overlap(manifest.rows),
                         "group_only_observed_cross_split":group_only_overlap(manifest.rows)})
    write_csv(args.output/"heldout_fixture_outcomes.csv",outcomes)
    for name,status in (("raw_clean","PASS"),("raw_exact_duplicate","FAIL"),("raw_digest_mismatch","FAIL")):
        report=audit_integrity(load_manifest(synthetic/(name+".csv")),verify_files=True,
                               data_root=synthetic/"raw_bytes",group_policy="disjoint")
        write_json(args.output/(name+".json"),report)
        check("raw_check:"+name,report["checks"]["raw_content"]["status"]==status)
    lineage_manifest=load_manifest(synthetic/"lineage_manifest.csv")
    for path in sorted(synthetic.glob("lineage_*.json")):
        declaration=json.loads(path.read_text(encoding="utf-8"))
        report=audit_integrity(lineage_manifest,lineage=declaration,group_policy="disjoint")
        if "unknown_labels" in path.stem:
            expected="UNKNOWN"
        elif "contamination" in path.stem or "target_labels" in path.stem:
            expected="FAIL"
        else:
            expected="PASS"
        check("declared_lineage:"+path.stem,report["checks"]["declared_lineage"]["status"]==expected)
        write_json(args.output/(path.stem+".json"),report)
    unequal=load_manifest(synthetic/"unequal_group_sizes.csv")
    low_budget=sample_indices(unequal,1,strategy="group",seed=41017)
    check("zero_draw_groups_counted",len(low_budget["group_exposures"])==4 and low_budget["groups_seen"]==1)
    check("population_CV_with_three_zero_groups",math.isclose(low_budget["draw_count_cv"],math.sqrt(3),abs_tol=1e-12))
    write_json(args.output/"zero_draw_group_check.json",low_budget)
    actual_class_rows=[]
    probability_map={"healthy":"prob_healthy","septoria":"prob_septoria","stripe_rust":"prob_stripe_rust"}
    for direction in ("JIC_to_Holeta","Holeta_to_JIC"):
        manifest=load_manifest(derived/f"wheat_{direction}_manifest.csv")
        predictions=load_predictions(derived/f"wheat_{direction}_predictions.csv")
        integrity=audit_integrity(manifest,group_policy="disjoint")
        # SVC.predict does not necessarily use predict_proba argmax. Preserve
        # supplied labels and explicitly refrain from declaring that rule.
        metrics=evaluate_predictions(predictions,manifest=manifest,bootstrap=args.bootstrap,seed=41017,
                                     unit="image",stratify=True,probability_columns=probability_map,decision_rule=None)
        check(direction+":group_identity_unknown",integrity["checks"]["groups"]["status"]=="UNKNOWN")
        check(direction+":raw_content_unknown",integrity["checks"]["raw_content"]["status"]=="UNKNOWN")
        check(direction+":probability_numeric_validity",metrics["probability_evidence"]["status"]=="PASS")
        write_json(args.output/f"wheat_{direction}_integrity.json",integrity)
        write_json(args.output/f"wheat_{direction}_metrics.json",metrics)
        if args.bootstrap==2000:
            expected_metrics=json.loads((REPOSITORY/f"reported_results/wheat_{direction}_metrics.json").read_text(encoding="utf-8"))
            for name in ("accuracy","balanced_accuracy","macro_f1_observed_truth_classes"):
                expected_interval=expected_metrics["bootstrap"]["intervals"][name]
                actual_interval=metrics["bootstrap"]["intervals"][name]
                for bound in ("lower","upper"):
                    check("wheat_fixed_interval:"+direction+":"+name+":"+bound,
                          math.isclose(expected_interval[bound],actual_interval[bound],abs_tol=1e-12))
        for item in metrics["metrics"]["per_class"]:
            actual_class_rows.append({"direction":direction.replace("_to_","→"),"class":item["label"],"n_true":item["n_true"],
                                      "n_correct":item["n_correct"],"recall":item["recall"],
                                      "balanced_accuracy":metrics["metrics"]["balanced_accuracy"],
                                      "n_predictions":metrics["metrics"]["n_predictions"],"identity_evidence":"UNKNOWN","bootstrap_unit":"image"})
    write_csv(args.output/"wheat_replay_class_metrics.csv",actual_class_rows)
    archived=read_csv(REPOSITORY/"reported_results/wheat_replay_class_metrics.csv")
    by_key={(row["direction"],row["class"]):row for row in archived}
    for row in actual_class_rows:
        expected=by_key[(row["direction"],row["class"])]
        for name in ("n_true","n_correct","n_predictions"):
            check("wheat_fixed_count:"+row["direction"]+":"+row["class"]+":"+name,int(expected[name])==row[name])
        for name in ("recall","balanced_accuracy"):
            check("wheat_fixed_metric:"+row["direction"]+":"+row["class"]+":"+name,math.isclose(float(expected[name]),row[name],abs_tol=1e-12))
    # Aggregated measured group counts are expanded into artificial bookkeeping
    # records solely to replay allocation; no original sample content is recreated.
    ledger=read_csv(derived/"U0_anonymous_group_size_ledger.csv")
    expanded=expand_group_counts(ledger)
    count_reports=[]
    for seed in (41017,41029,41041):
        for strategy in ("image","episode"):
            report=sample_indices(expanded,26500,strategy=strategy,seed=seed,splits=("train",))
            count_reports.append({"strategy":strategy,"seed":seed,"n_draws":report["n_draws"],"n_groups":report["n_groups"],
                                  "CV_including_zeros":report["draw_count_cv"],"spearman_size_draws":report["spearman_group_size_vs_draws"],
                                  "zero_draw_groups":sum(item["n_draws"]==0 for item in report["group_exposures"])})
    write_csv(args.output/"U0_aggregate_allocation_replay.csv",count_reports)
    archived=read_csv(REPOSITORY/"reported_results/wheat_U0_software_sampling_replay.csv")
    by_key={(row["strategy"],int(row["seed"])):row for row in archived}
    for row in count_reports:
        expected=by_key[(row["strategy"],row["seed"])]
        for name in ("CV_including_zeros","spearman_size_draws"):
            check("allocation_replay:"+row["strategy"]+":"+str(row["seed"])+":"+name,math.isclose(float(expected[name]),row[name],abs_tol=1e-12))
    for name,policy,expected in (("coil20_identity_disjoint","disjoint","PASS"),
                                  ("coil20_shared_identity_pose_split","disjoint","FAIL"),
                                  ("coil20_shared_identity_pose_split","overlap_allowed","PASS"),
                                  ("coil20_shared_identity_pose_split","unspecified","UNKNOWN")):
        report=audit_integrity(load_manifest(derived/(name+".csv")),group_policy=policy,
                               verify_files=args.coil_raw is not None,data_root=args.coil_raw)
        check("COIL_protocol:"+policy+":"+name,report["checks"]["groups"]["status"]==expected)
        if args.coil_raw is None:
            check("COIL_raw_not_distributed:"+policy+":"+name,report["checks"]["raw_content"]["status"]=="UNKNOWN")
        write_json(args.output/(name+"__"+policy+".json"),report)
    summary={"software_checks":len(checks),"failed_checks":sum(not item["passed"] for item in checks),"checks":checks,
             "n_frozen_fixture_cases":len(outcomes),"n_U0_aggregate_groups":len(ledger),"n_U0_expanded_bookkeeping_records":len(expanded),
             "historical_models_retrained":False,"original_COIL_images_distributed":False,"original_U0_images_distributed":False,
             "limitations":["This convenience replay is not a new independent validation team or field collection.",
                            "Wheat predictions are retrospective fixed outputs, not an untouched prospective result.",
                            "Anonymous group-count expansion is artificial bookkeeping representing aggregate counts, not image reconstruction.",
                            "No raw wheat pixels or institutional identities/pathology are verified by replay.",
                            "Archived runtime and external-library baseline results are not regenerated by this default NumPy-only script."]}
    write_json(args.output/"REPLAY_SUMMARY.json",summary)
    print(json.dumps({key:summary[key] for key in ("software_checks","failed_checks","n_frozen_fixture_cases","n_U0_aggregate_groups")},indent=2))
    return int(summary["failed_checks"]>0)


if __name__=="__main__":
    raise SystemExit(main())
