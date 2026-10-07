"""Optional original-provider download, with no redistribution permission claim."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.request import urlopen
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination",type=Path,required=True)
    args=parser.parse_args()
    record=json.loads((ROOT/"data/derived/COIL20_PROVENANCE.json").read_text(encoding="utf-8"))
    with urlopen(record["original_url"],timeout=120) as response:
        blob=response.read()
    if hashlib.sha256(blob).hexdigest()!=record["archive_sha256"]:
        raise ValueError("Original archive digest changed; stop and review upstream provenance rather than silently use another version.")
    archive=zipfile.ZipFile(io.BytesIO(blob))
    members=[name for name in archive.namelist() if re.fullmatch(r"obj\d+__\d+\.png",Path(name).name)]
    if len(members)!=record["image_count"] or len({Path(name).name for name in members})!=len(members):
        raise ValueError("Unexpected image count or duplicate basenames in official archive.")
    images=args.destination/"images"
    images.mkdir(parents=True,exist_ok=True)
    for member in members:
        target=images/Path(member).name
        content=archive.read(member)
        if target.exists() and target.read_bytes()!=content:
            raise ValueError("Destination contains different existing bytes; choose an empty directory.")
        target.write_bytes(content)
    receipt={"source_url":record["original_url"],"archive_sha256":record["archive_sha256"],"n_images":len(members),
             "redistribution_permission":"NOT_ESTABLISHED","warning":"Local download only; respect original-provider terms and do not treat this receipt as a republishing license."}
    (args.destination/"download_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2))

if __name__=="__main__":
    main()
