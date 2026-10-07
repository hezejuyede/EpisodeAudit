"""Record actually reached application assertions during a genuine local replay.

No core source is modified and assertions are not rewritten or bypassed.
Download is disabled by default in the application; source metadata is local.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import argparse,ast,contextlib,hashlib,io,json,sys,traceback

PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT/'replayed_results'/'har'
parser=argparse.ArgumentParser(description='Trace the local HAR application only after explicit upstream-data opt-in.')
parser.add_argument('--opt-in-upstream-data',action='store_true')
args=parser.parse_args()
if not args.opt_in_upstream_data:
    parser.error('No automatic HAR download or parsing. Add --opt-in-upstream-data only after reviewing both upstream notices.')
script=PROJECT/'scripts/run_har_application.py'
source=script.read_text(encoding='utf-8')
parsed=ast.parse(source)
assertions={node.lineno:ast.get_source_segment(source,node) for node in ast.walk(parsed) if isinstance(node,ast.Assert)}
counts=Counter()
def trace(frame,event,arg):
    if event=='line' and frame.f_code.co_filename==str(script) and not frame.f_code.co_name.startswith('<') and frame.f_lineno in assertions:
        counts[frame.f_lineno]+=1
    return trace

started=datetime.now(timezone.utc).isoformat()
output=io.StringIO(); failure=None
sys.argv=[str(script),'--audit','--opt-in-upstream-data','--runtime-freeze',str(PROJECT/'provenance/CORRECTIVE_FREEZE_20261007.json')]
try:
    sys.settrace(trace)
    with contextlib.redirect_stdout(output):
        exec(compile(source,str(script),'exec'),{'__name__':'__main__','__file__':str(script)})
except BaseException:
    failure=traceback.format_exc()
finally:
    sys.settrace(None)
receipt={'phase':'SECOND_ROUND_HAR_FINAL_REPLAY','started_at_utc':started,
    'finished_at_utc':datetime.now(timezone.utc).isoformat(),
    'status':'COMPLETED' if failure is None else 'ERROR',
    'execution_error_count':0 if failure is None else 1,
    'executed_application_assertion_line_events':sum(counts.values()),
    'distinct_application_assertions_reached':len(counts),
    'reached_assertions':[{'line':line,'executions':count,'statement':assertions[line],
        'all_completed_without_assertion_error':failure is None} for line,count in sorted(counts.items())],
    'trace_boundary':'Counts application Assert statement line events, excluding generator/comprehension frames. Core source and library assertions are not counted. With an error-free replay all listed assertion executions completed without raising.',
    'application_script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),
    'postrun_control_plan_sha256':hashlib.sha256((PROJECT/'provenance/HAR_PROTOCOL_PLANS.json').read_bytes()).hexdigest(),
    'stdout':output.getvalue(),'error':failure,
    'separate_from_original_453_assertions':True,
    'scientific_boundary':'Expected UNKNOWN and intentional fault FAIL states are preserved; zero execution errors do not mean all evidence gates pass.'}
(ROOT/'HAR_FINAL_EXECUTION_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'reached_assertions','stdout','error'}},indent=2))
if failure is not None:
    print(failure,file=sys.stderr)
    raise SystemExit(1)
