"""One bounded official download, retained locally and excluded from all packages."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, shutil, subprocess, time

PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT/'replayed_results'/'har'
URL='https://archive.ics.uci.edu/static/public/240/human%2Bactivity%2Brecognition%2Busing%2Bsmartphones.zip'
parser=argparse.ArgumentParser(description='Optional local-only UCI HAR download; not a redistribution of upstream data.')
parser.add_argument('--opt-in-upstream-data',action='store_true')
args=parser.parse_args()
if not args.opt_in_upstream_data:
    parser.error('No automatic download. Current UCI record states CC BY 4.0; the original archive prohibits commercial use. Review both notices and explicitly add --opt-in-upstream-data only for your own permitted local use.')
LOCAL=ROOT/'source_cache'
LOCAL.mkdir(parents=True,exist_ok=True)
final_path=LOCAL/'official_UCI_download.zip'
expected_bytes=61005872
expected_sha='c00b803081a5c797cd5e4b83700a9810b38d53d9d84e01917e090e1fdbc81031'
def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): hasher.update(block)
    return hasher.hexdigest()
if final_path.exists() and final_path.stat().st_size==expected_bytes and digest(final_path)==expected_sha:
    receipt={'status':'CACHE_REUSED_RECORDED_OFFICIAL_BYTES','source_url':URL,
        'local_file':final_path.relative_to(ROOT).as_posix(),'bytes_retained_locally':expected_bytes,
        'sha256_of_retained_file':expected_sha,'new_network_download_performed':False,
        'curl_exit_code':None,'complete_zip_or_member_crc_verified_by_this_command':False,
        'exclude_entire_local_directory_from_master_and_public_packages':True}
    (ROOT/'HAR_LONG_BOUNDED_DOWNLOAD_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2)); raise SystemExit(0)
# Never truncate a known cache inode: validation may use a local hard link.
path=LOCAL/'official_UCI_download.zip.part'
headers=LOCAL/'response_headers.txt'
started=datetime.now(timezone.utc).isoformat()
plan={'status':'RUNNING','started_at_utc':started,'source_url':URL,'max_time_seconds':600,
      'local_file':path.relative_to(ROOT).as_posix(),
      'exclude_entire_local_directory_from_master_and_public_packages':True}
(ROOT/'HAR_LONG_BOUNDED_DOWNLOAD_STARTED.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
clock=time.monotonic()
result=subprocess.run([shutil.which('curl.exe') or shutil.which('curl'),'--ipv4','--fail','--location',
    '--silent','--show-error','--connect-timeout','20','--max-time','600',
    '--output',str(path),'--dump-header',str(headers),URL],capture_output=True,timeout=615)
payload_sha=digest(path) if path.exists() else None
version_matches=(path.exists() and path.stat().st_size==expected_bytes and payload_sha==expected_sha)
if result.returncode==0 and version_matches:
    path.replace(final_path)
    path=final_path
receipt={**plan,'status':('DOWNLOADED_AWAITING_ZIP_VERIFICATION' if version_matches else 'SOURCE_VERSION_CHANGED') if result.returncode==0 else 'NOT_COMPLETED',
    'local_file':path.relative_to(ROOT).as_posix(),
    'finished_at_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-clock,
    'curl_exit_code':result.returncode,'bytes_retained_locally':path.stat().st_size if path.exists() else 0,
    'sha256_of_retained_file':payload_sha,
    'recorded_official_source_version_matches':version_matches,
    'stderr':result.stderr.decode('utf-8',errors='replace'),
    'http_response_headers':headers.read_text() if headers.exists() else None,
    'complete_zip_or_member_crc_verified':False,
    'boundary':'Local-only source payload. A successful curl exit does not replace archive CRC verification.'}
(ROOT/'HAR_LONG_BOUNDED_DOWNLOAD_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt,indent=2))
raise SystemExit(result.returncode if result.returncode else (0 if version_matches else 2))
