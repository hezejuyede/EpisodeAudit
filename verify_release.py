"""Verify the local candidate's file index; not a signed provenance authority."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INDEX=ROOT/"provenance/RELEASE_FILE_INDEX.json"
IGNORED={".git","__pycache__","build","dist",".venv","replayed_results","replayed_deepchecks_results","local-coil20","figures"}

def included(path):
    relative=path.relative_to(ROOT)
    return not any(part in IGNORED or part.endswith(".egg-info") for part in relative.parts)

def main():
    record=json.loads(INDEX.read_text(encoding="utf-8"))
    failures=[]
    expected=set()
    for item in record["files"]:
        expected.add(item["path"])
        path=ROOT/item["path"]
        if not path.is_file():
            failures.append({"path":item["path"],"reason":"missing"})
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            failures.append({"path":item["path"],"reason":"digest_mismatch"})
    observed={path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file() and included(path) and path!=INDEX}
    for path in sorted(observed-expected):
        failures.append({"path":path,"reason":"not_in_index"})
    print(json.dumps({"n_indexed_files":len(expected),"n_failures":len(failures),"failures":failures,
                      "boundary":"Index consistency only; no digital signature, remote archive or third-party certification is asserted."},indent=2))
    return int(bool(failures))

if __name__=="__main__":
    raise SystemExit(main())
