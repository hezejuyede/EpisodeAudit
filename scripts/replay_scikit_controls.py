"""Original scikit-learn split APIs on released COIL object metadata, no pixels."""
from pathlib import Path
import argparse
import csv
import json
import numpy as np
import sklearn
from sklearn.model_selection import ShuffleSplit, GroupShuffleSplit

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    with path.open(encoding="utf-8",newline="") as stream:
        return list(csv.DictReader(stream))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"replayed_results")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    rows=read(ROOT/"data/derived/coil20_identity_disjoint.csv")
    groups=np.asarray([row["group_id"] for row in rows])
    x=np.arange(len(rows)).reshape(-1,1)
    seeds=json.loads((ROOT/"data/synthetic/VALIDATION_PLAN_FROZEN.json").read_text(encoding="utf-8"))["held_out_fixture_seeds"]
    outcomes=[]
    for seed in seeds:
        for name,splitter in (("ShuffleSplit",ShuffleSplit(n_splits=1,test_size=.25,random_state=seed)),
                              ("GroupShuffleSplit",GroupShuffleSplit(n_splits=1,test_size=.25,random_state=seed))):
            train,test=next(splitter.split(x,groups=groups))
            overlap=len(set(groups[train]).intersection(groups[test]))
            outcomes.append({"library":"scikit-learn","version":sklearn.__version__,"splitter":name,"seed":seed,
                             "n_train":len(train),"n_test":len(test),"n_shared_object_ids":overlap})
    path=args.output/"actual_sklearn_COIL20_split_controls.csv"
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(outcomes[0]),lineterminator="\n")
        writer.writeheader();writer.writerows(outcomes)
    archived=read(ROOT/"reported_results/actual_sklearn_COIL20_split_controls.csv")
    expected={(row["splitter"],int(row["seed"])):row for row in archived}
    matched=all(all(int(expected[(row["splitter"],row["seed"])][key])==row[key] for key in ("n_train","n_test","n_shared_object_ids")) for row in outcomes)
    summary={"n_original_API_runs":len(outcomes),"numeric_reference_match":matched,"version":sklearn.__version__,
             "raw_pixels_used":False,"limitation":"Shared objects are appropriate for known-object/new-view classification; disjoint objects test a different estimand."}
    (args.output/"SCIKIT_CONTROL_REPLAY_SUMMARY.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return int(not matched)

if __name__=="__main__":
    raise SystemExit(main())
