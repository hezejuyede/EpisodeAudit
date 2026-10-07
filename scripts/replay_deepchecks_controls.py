"""Execute original Deepchecks APIs on matched, explicitly adapted fixtures.

The selected checks cover exact feature-row and provided-index overlap. This
does not benchmark all Deepchecks functionality or show universal superiority.
No Deepchecks source code is copied into EpisodeAudit or monkeypatched.
"""
from pathlib import Path
import base64
import collections
import csv
import hashlib
import json
import sys
import time
import traceback
import warnings
import argparse

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT / 'replayed_deepchecks_results'

def read(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def write(path,rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        fields=list(dict.fromkeys(k for r in rows for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def scoped_token(row):
    return json.dumps(["explicit",row["group_namespace"],row["group_id"]] if row.get("group_namespace") else ["collection",row["collection_id"],row["group_id"]],separators=(",",":"))

def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    OUTPUT=args.output
    OUTPUT.mkdir(parents=True,exist_ok=True)
    try:
        import numpy as np
        import pandas as pd
        import scipy
        import sklearn
        import deepchecks
        import category_encoders
        from deepchecks.tabular import Dataset
        from deepchecks.tabular.checks import TrainTestSamplesMix, IndexTrainTestLeakage
        from importlib import metadata
        from episodeaudit import load_manifest, audit_integrity
        check_record=[]
        distribution=metadata.distribution("deepchecks")
        for member in distribution.files:
            if str(member).startswith("deepchecks/") and member.hash is not None:
                blob=distribution.locate_file(member).read_bytes()
                computed=base64.urlsafe_b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
                check_record.append({"path":str(member),"hash_match":computed==member.hash.value})
        assert all(r["hash_match"] for r in check_record),"Original Deepchecks wheel-record mismatch"
        receipt=json.loads((ROOT/"data/synthetic/FIXTURE_FREEZE_RECEIPT.json").read_text(encoding="utf-8"))
        specs=receipt["cases"]
        outcomes=[]
        warning_counts=collections.Counter()
        def run_original(check,train,test):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result=check.run(train,test,with_display=False)
            warning_counts.update(type(w.message).__name__+": "+str(w.message) for w in caught)
            return result
        def datasets(rows,index_name=None):
            data=[]
            for r in rows:
                # Two digest halves keep features exact and prevent field tuples
                # from being mistaken for ordinal biological measurements.
                d={"digest_prefix":r.get("sha256","")[:32],"digest_suffix":r.get("sha256","")[32:]}
                if index_name:
                    d[index_name]=json.dumps([r["collection_id"],r["sample_id"]],separators=(",",":")) if index_name=="provided_membership_token" else scoped_token(r)
                data.append(d)
            return Dataset(pd.DataFrame(data),features=["digest_prefix","digest_suffix"],cat_features=["digest_prefix","digest_suffix"],index_name=index_name)
        for spec in specs:
            path=ROOT/"data/synthetic"/spec["file"];rows=read(path)
            train=[r for r in rows if r["split"]=="train"];test=[r for r in rows if r["split"]=="test"]
            audit=audit_integrity(load_manifest(path),group_policy="disjoint")
            started=time.perf_counter()
            content=run_original(TrainTestSamplesMix(random_state=spec["seed"]),datasets(train),datasets(test))
            hash_ratio=float(content.value["ratio"])
            hash_elapsed=time.perf_counter()-started
            group_ratio=None;group_reason="missing_group_identifier"
            if all(r.get("group_id") for r in rows):
                started=time.perf_counter()
                grouped=run_original(IndexTrainTestLeakage(random_state=spec["seed"]),datasets(train,index_name="provided_group_token"),datasets(test,index_name="provided_group_token"))
                group_ratio=float(grouped.value)
                group_elapsed=time.perf_counter()-started;group_reason="executed"
            else:group_elapsed=None
            member=run_original(IndexTrainTestLeakage(random_state=spec["seed"]),datasets(train,index_name="provided_membership_token"),datasets(test,index_name="provided_membership_token"))
            member_ratio=float(member.value)
            # Interpret actual check ratios only as overlap detection, never as
            # calibrated error probabilities or scientific validity judgements.
            outcomes.append({"seed":spec["seed"],"family":spec["family"],"n_rows":len(rows),
                             "deepchecks_samples_mix_ratio":hash_ratio,"deepchecks_samples_mix_detects":hash_ratio>0,
                             "deepchecks_group_index_ratio":group_ratio,"deepchecks_group_index_detects":None if group_ratio is None else group_ratio>0,
                             "deepchecks_membership_index_ratio":member_ratio,"deepchecks_membership_index_detects":member_ratio>0,
                             "group_adapter_status":group_reason,"hash_check_seconds":hash_elapsed,"group_check_seconds":group_elapsed,
                             "episodeaudit_provided_hash_status":audit["checks"]["provided_hashes"]["status"],
                             "episodeaudit_group_status":audit["checks"]["groups"]["status"],
                             "episodeaudit_membership_status":audit["checks"]["membership"]["status"]})
        write(OUTPUT/"actual_deepchecks_matched_outcomes.csv",outcomes)
        summaries=[]
        for family in sorted({r["family"] for r in outcomes}):
            rs=[r for r in outcomes if r["family"]==family]
            summaries.append({"family":family,"n_cases":len(rs),
                              "n_Deepchecks_samples_mix_overlap":sum(r["deepchecks_samples_mix_detects"] for r in rs),
                              "n_Deepchecks_group_index_overlap":sum(r["deepchecks_group_index_detects"] is True for r in rs),
                              "n_Deepchecks_group_not_run_missing_evidence":sum(r["deepchecks_group_index_detects"] is None for r in rs),
                              "n_Deepchecks_membership_index_overlap":sum(r["deepchecks_membership_index_detects"] for r in rs),
                              "n_EpisodeAudit_hash_FAIL":sum(r["episodeaudit_provided_hash_status"]=="FAIL" for r in rs),
                              "n_EpisodeAudit_group_FAIL_declared_disjoint":sum(r["episodeaudit_group_status"]=="FAIL" for r in rs),
                              "n_EpisodeAudit_membership_FAIL":sum(r["episodeaudit_membership_status"]=="FAIL" for r in rs)})
        write(OUTPUT/"actual_deepchecks_family_summary.csv",summaries)
        versions={"deepchecks":deepchecks.__version__,"numpy":np.__version__,"pandas":pd.__version__,"scipy":scipy.__version__,"scikit-learn":sklearn.__version__,"category-encoders":category_encoders.__version__,"setuptools":metadata.version("setuptools")}
        report={"status":"EXECUTED","n_matched_cases":len(outcomes),"n_seed_variants":20,"versions":versions,
                "original_source_record_files":len(check_record),"original_source_record_mismatches":sum(not r["hash_match"] for r in check_record),
                "checks":["deepchecks.tabular.checks.TrainTestSamplesMix","deepchecks.tabular.checks.IndexTrainTestLeakage"],
                "input_adapter":"Unlabelled tabular features are two halves of supplied SHA-256 strings. Original IndexTrainTestLeakage is run twice, once with namespace-aware group keys and once with collection/sample membership keys as the index. No actual pixel inputs or Deepchecks vision-suite benchmark.",
                "group_ratio_definition":"Deepchecks IndexTrainTestLeakage reports number of distinct intersecting index values divided by number of test rows, not fraction of test rows belonging to overlapping groups.",
                "limitations":["Selected exact/index overlap checks, not all Deepchecks functionality.","Digest features are provided strings, not verified raw image content.","Missing group inputs skip group-index checks; this is unavailable evidence rather than failure of the external tool.","Overlap detection is interpreted against a declared group-disjoint protocol; known-object/new-view recognition can legitimately share identities.","Lineage, exposure and class reports are outside these selected checks; cannot infer all of Deepchecks lacks alternatives or extensions.","No throughput claim across tools; selected adapters and dependency stacks differ."],
                "captured_upstream_warning_counts":dict(warning_counts),
                "comparison_expansion":"A third run using membership keys as the provided index was added after the first external-tool execution to avoid weakening a baseline that can natively audit more than one index semantic. Original overlap figures remain unchanged.",
                "compatibility":"Pinned NumPy1.26.4/pandas2.2.3/SciPy1.14.1/scikit-learn1.5.2/setuptools80.9.0/category-encoders2.6.4 after recorded dependency incompatibilities. Original library source unmodified; no monkeypatches."}
        (OUTPUT/"DEEPCHECKS_EXECUTION_RECEIPT.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps({"status":"EXECUTED","n_cases":len(outcomes),"versions":versions}))
    except Exception as error:
        report={"status":"UNAVAILABLE_OR_FAILED","error_type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc(),"executed_successfully":False}
        (OUTPUT/"DEEPCHECKS_EXECUTION_RECEIPT.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps({"status":report["status"],"error_type":report["error_type"],"message":str(error)}))
        raise SystemExit(1)

if __name__=="__main__":main()
