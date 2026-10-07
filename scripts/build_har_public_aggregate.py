"""Export own aggregate software outputs; do not redistribute upstream HAR rows."""
from pathlib import Path
from collections import Counter
import argparse,csv,hashlib,json

PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT/'replayed_results'/'har'
parser=argparse.ArgumentParser(description='Export aggregate outputs from an explicitly opted-in local HAR replay.')
parser.add_argument('--opt-in-upstream-data',action='store_true')
args=parser.parse_args()
if not args.opt_in_upstream_data:
    parser.error('No automatic parsing of local HAR-derived rows. Add --opt-in-upstream-data after reviewing both upstream notices.')
def read(name):
    return json.loads((ROOT/name).read_text(encoding='utf-8'))
summary=read('SECOND_ROUND_HAR_SUMMARY.json')
execution=read('HAR_FINAL_EXECUTION_RECEIPT.json')
assert execution['status']=='COMPLETED' and execution['execution_error_count']==0
assert execution['application_script_sha256']==summary['application_script_sha256']
provenance=read('HAR_DOWNLOAD_PROVENANCE.json')
assert provenance['outer_zip_crc_pass'] and provenance['original_dataset_zip_crc_pass']
with (ROOT/'har_official_test_constant_predictions.csv').open(encoding='utf-8',newline='') as stream:
    test_activity_counts=Counter(row['y_true'] for row in csv.DictReader(stream))
metrics=read('results/official_test_constant_metrics.json')
protocol_files=['official_unspecified','official_disjoint','constructed_train_shuffle_disjoint',
                'restored_official_disjoint','fault_transform_missing_split',
                'repaired_transform_official_membership','heldout_label_using_transform']
protocols={}
for name in protocol_files:
    report=read('results/'+name+'.json')
    protocols[name]={'aggregate_computational_status':report['status'],
        'check_states':{key:value['status'] for key,value in report['checks'].items()},
        'physical_identity_evidence':report['identity_evidence']['status'],
        'unobserved_execution_leakage':report['execution_leakage']['status']}
sampling={}
for strategy in ['image','group']:
    report=read('results/exposure_'+strategy+'.json')
    sampling[strategy]={'n_draws':report['n_draws'],'replacement':report['replacement'],
        'n_provided_subject_groups':report['n_groups'],'groups_seen':report['groups_seen'],
        'draw_count_cv':report['draw_count_cv'],'seed':report['seed'],
        'boundary':'Allocation only. The two replacement settings differ; no classifier-training or prediction-improvement effect is measured.'}
public={'phase':'SECOND_ROUND_HAR_METADATA_WORKFLOW','status':'EXECUTED_LOCAL_ONLY_WITH_REDISTRIBUTION_HOLD',
    'dependency_versions':read('HAR_INDEPENDENT_METADATA_ORACLES.json')['versions'],
    'source':{'title':'Human Activity Recognition Using Smartphones','doi':'10.24432/C54S4K',
        'url':'https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones',
        'download_sha256_locally_computed':provenance['download_sha256'],
        'full_outer_and_inner_zip_crc_verified':True,
        'http_content_length':provenance['http_content_length'],
        'http_content_length_verification':provenance['http_content_length_verification'],
        'hash_boundary':'Local provenance, not a checksum or signature published by UCI.'},
    'official_aggregate_counts':{'n_repeated_windows':summary['official_counts']['n_records'],
        'n_provided_participants':len(set(summary['official_counts']['train_subjects'])|set(summary['official_counts']['test_subjects'])),
        'n_training_windows':summary['official_counts']['n_train_rows'],'n_test_windows':summary['official_counts']['n_test_rows'],
        'n_training_participants':len(summary['official_counts']['train_subjects']),
        'n_test_participants':len(summary['official_counts']['test_subjects']),
        'n_shared_participants':len(summary['official_counts']['overlapping_subjects_set_oracle']),
        'n_activities':summary['official_counts']['n_activities'],
        'set_and_crosstab_oracles_agree':summary['official_counts']['oracles_agree']},
    'constructed_fault_aggregate_counts':{'uses_only_original_training_windows':True,
        'n_repeated_windows':summary['constructed_counts']['n_records'],
        'n_constructed_train_windows':summary['constructed_counts']['n_train_rows'],
        'n_constructed_test_windows':summary['constructed_counts']['n_test_rows'],
        'n_shared_participants':len(summary['constructed_counts']['overlapping_subjects_set_oracle']),
        'set_and_crosstab_oracles_agree':summary['constructed_counts']['oracles_agree'],
        'seed':72007,'construction':'Actual scikit-learn ShuffleSplit, test_size=0.30; our explicit fault, not the original UCI protocol.'},
    'protocol_states':protocols,
    'postrun_transform_controls':{'status_timing':'Exploratory controls declared in a dated addendum after initial results were known.',
        'missing_training_transform_split':summary['fault_transform_declared_lineage'],
        'same_declaration_with_repaired_official_membership':summary['repaired_transform_declared_lineage'],
        'genuine_heldout_label_transform':summary['heldout_label_transform_declared_lineage'],
        'heldout_finding_reasons':summary['heldout_label_transform_finding_reasons'],
        'boundary':'Declared protocol evidence changes. Actual model training and historical label access are not independently observed.'},
    'sampling_aggregate':sampling,
    'fixed_constant_rule':{'type':summary['constant_rule']['type'],
        'selection':'Official training activity frequency only; ties smallest activity ID.',
        'selected_activity':summary['constant_rule']['selected_activity_label'],
        'training_activity_counts_by_original_activity_id':summary['constant_rule']['training_activity_counts'],
        'test_activity_counts':dict(sorted(test_activity_counts.items())),
        'test_used_to_choose_rule':False,'balanced_accuracy':summary['constant_balanced_accuracy'],
        'accuracy':summary['constant_accuracy'],'actual_sklearn_oracle_matches':summary['independent_sklearn_metric_oracle_matches'],
        'bootstrap':metrics['bootstrap'],
        'boundary':'Metric joining demonstration with a fixed constant rule. BA=1/6 is analytic; the degenerate BA interval does not show generalization or classifier superiority.'},
    'execution':{'status':execution['status'],'execution_error_count':execution['execution_error_count'],
        'executed_application_assertion_line_events':execution['executed_application_assertion_line_events'],
        'distinct_application_assertions_reached':execution['distinct_application_assertions_reached'],
        'count_boundary':execution['trace_boundary'],'separate_from_original_453_assertions':True},
    'reproduction_fingerprints':{'application_script_sha256':summary['application_script_sha256'],
        'corrective_freeze_sha256':summary['runtime_freeze_sha256'],
        'eight_runtime_source_sha256':summary['runtime_source_sha256'],
        'postrun_control_plan_sha256':execution['postrun_control_plan_sha256']},
    'rights':{'redistribution_status':'HOLD_UNRESOLVED_UPSTREAM_NOTICE_DISCREPANCY',
        'current_UCI_record_claim':'CC BY 4.0','original_README_and_names_notice':'Any commercial use is prohibited.',
        'no_raw_or_row_level_derived_HAR_metadata_bundled':True,
        'software_MIT_does_not_apply_to_upstream_HAR_data':True,
        'local_download':'Explicit opt-in from the official free source only, after reviewing both notices.'},
    'scientific_boundary':'One genuine non-image repeated-measurement metadata application. No sensor-feature model, independently recruited participants, physical identity reauthentication, external-user adoption, plant/pathology validation, algorithm superiority or future-domain accuracy claim.'}
(ROOT/'HAR_PUBLIC_AGGREGATE_SUMMARY.json').write_text(json.dumps(public,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps({'status':public['status'],'n_windows':public['official_aggregate_counts']['n_repeated_windows'],
    'source_participants':public['official_aggregate_counts']['n_provided_participants'],
    'original_subject_ID_lists_exported':False,'row_level_metadata_exported':False}))
