"""Metadata-only HAR application. No sensor extraction or sensor-feature model.

Run preparation before the corrected-runtime audit:
    python scripts/run_har_application.py --prepare-only --opt-in-upstream-data
    python scripts/run_har_application.py --audit --opt-in-upstream-data
All project data paths are relative to this script; no private original image data.
"""
from pathlib import Path
from collections import Counter
import argparse, copy, csv, hashlib, io, json, sys, urllib.request, zipfile, shutil, subprocess
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT/'replayed_results'/'har'
EXPECTED_SOURCE_SHA256 = 'c00b803081a5c797cd5e4b83700a9810b38d53d9d84e01917e090e1fdbc81031'
EXPECTED_SOURCE_BYTES = 61005872
URL = 'https://archive.ics.uci.edu/static/public/240/human%2Bactivity%2Brecognition%2Busing%2Bsmartphones.zip'
PRIMARY = 'https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones'
SEED = 72007

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save_json(name, value):
    (ROOT/name).parent.mkdir(parents=True, exist_ok=True)
    (ROOT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def save_csv(name, rows, fields):
    with (ROOT/name).open('w', encoding='utf-8', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

def prepare(local_archive):
    # Only an explicitly opted-in local cache is parsed. The recorded official
    # source version is checked before CRC or member extraction.
    archive_path=Path(local_archive).resolve()
    permitted_path=(ROOT/'source_cache'/'official_UCI_download.zip').resolve()
    assert archive_path==permitted_path, 'Use the ignored local cache, never a bundled upstream archive.'
    outer=archive_path.read_bytes()
    assert len(outer)==EXPECTED_SOURCE_BYTES and sha(outer)==EXPECTED_SOURCE_SHA256, 'Official source version differs from the recorded publication artifact.'
    headers={}; resolved=URL
    client='Explicit local opt-in; recorded official archive bytes matched before full CRC verification'
    declared=headers.get('Content-Length') or headers.get('content-length')
    if declared is not None:
        assert len(outer)==int(declared), 'Download does not match HTTP Content-Length'
    outer_zip=zipfile.ZipFile(io.BytesIO(outer))
    assert outer_zip.testzip() is None, 'Outer archive CRC failure'
    inner_names=[name for name in outer_zip.namelist() if Path(name).name.lower()=='uci har dataset.zip']
    if inner_names:
        inner=outer_zip.read(inner_names[0]); archive=zipfile.ZipFile(io.BytesIO(inner))
    else:
        inner=outer; archive=outer_zip
    assert archive.testzip() is None, 'Dataset archive CRC failure'
    selected=['README.txt','activity_labels.txt','train/subject_train.txt','train/y_train.txt','test/subject_test.txt','test/y_test.txt']
    records=[]
    for suffix in selected:
        choices=[name for name in archive.namelist() if name.endswith('/'+suffix) or name==suffix]
        assert len(choices)==1, 'Ambiguous/missing metadata '+suffix
        blob=archive.read(choices[0])
        local=ROOT/'source_metadata'/suffix
        local.parent.mkdir(parents=True, exist_ok=True); local.write_bytes(blob)
        info=archive.getinfo(choices[0])
        records.append({'archive_member':choices[0],'local_file':local.relative_to(ROOT).as_posix(),
            'bytes':len(blob),'sha256':sha(blob),'zip_crc32':f'{info.CRC:08x}',
            'archive_layer':'inner_dataset' if inner_names else 'official_download',
            'archive_member_uncompressed_bytes':info.file_size,'archive_member_compressed_bytes':info.compress_size})
    # The official outer bundle also supplies its original .names description.
    # Preserve that small source/rights notice without extracting sensor data.
    outer_notice_names=[name for name in outer_zip.namelist() if not name.endswith('/') and (
        Path(name).suffix.lower()=='.names' or any(term in Path(name).name.lower()
        for term in ['license','licence','copyright','notice']))]
    outer_notices={}
    for name in outer_notice_names:
        blob=outer_zip.read(name); info=outer_zip.getinfo(name)
        outer_notices[name]=blob.decode('utf-8',errors='replace')
        local=ROOT/'source_metadata'/'outer_notices'/Path(name).name
        local.parent.mkdir(parents=True,exist_ok=True); local.write_bytes(blob)
        records.append({'archive_member':name,'local_file':local.relative_to(ROOT).as_posix(),
            'bytes':len(blob),'sha256':sha(blob),'zip_crc32':f'{info.CRC:08x}',
            'archive_layer':'official_download','archive_member_uncompressed_bytes':info.file_size,
            'archive_member_compressed_bytes':info.compress_size})
    feature_names=[name for name in archive.namelist() if name.endswith('/features.txt') or name=='features.txt']
    assert len(feature_names)==1
    n_feature_names=len(archive.read(feature_names[0]).decode('utf-8').splitlines())
    assert n_feature_names==561
    notice_members=[name for name in archive.namelist() if any(s in Path(name).name.lower() for s in ['license','licence','copyright','notice'])]
    archive_notices={name:archive.read(name).decode('utf-8',errors='replace') for name in notice_members if not name.endswith('/')}
    save_json('HAR_DOWNLOAD_PROVENANCE.json',{
        'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'primary_url':PRIMARY,'doi':'10.24432/C54S4K',
        'download_url':URL,'resolved_download_url':resolved,'download_client':client,'download_bytes':len(outer),'download_sha256':sha(outer),
        'http_content_length':declared,
        'http_content_length_matches':None if declared is None else len(outer)==int(declared),
        'http_content_length_verification':'UNKNOWN' if declared is None else 'PASS',
        'outer_zip_crc_pass':True,'original_dataset_archive_sha256':sha(inner),'original_dataset_zip_crc_pass':True,
        'metadata_files':records,'feature_name_count_checked_without_extraction':n_feature_names,
        'source_archive_notices':archive_notices,'outer_source_notices':outer_notices,
        'only_metadata_and_source_notices_extracted':True,
        'original_zip_retained_local_only':local_archive is not None,
        'local_only_source_directory_excluded_from_all_packages':local_archive is not None,
        'excluded':'No X_train/X_test or inertial signal files extracted to disk, no model embeddings generated. A local-only source ZIP, if supplied, is excluded from all master/public packages.',
        'hash_boundary':'SHA-256 is locally computed provenance, not a checksum published by UCI.'})

def rows_from_metadata():
    meta=ROOT/'source_metadata'
    labels={int(line.split()[0]):line.split()[1] for line in (meta/'activity_labels.txt').read_text().splitlines() if line.strip()}
    rows=[]
    for split in ['train','test']:
        subjects=[int(s) for s in (meta/split/('subject_'+split+'.txt')).read_text().split()]
        activities=[int(s) for s in (meta/split/('y_'+split+'.txt')).read_text().split()]
        assert len(subjects)==len(activities)
        assert all(1<=x<=30 for x in subjects) and all(x in labels for x in activities)
        for position,(subject,activity) in enumerate(zip(subjects,activities),1):
            rows.append({'sample_id':f'{split}_{position:06d}','collection_id':'UCI_HAR_240','label':labels[activity],
                'group_id':f'subject_{subject:02d}','group_kind':'identity','group_namespace':'UCI-HAR-participant',
                'split':split,'subject_id':str(subject),'activity_id':str(activity),'source_split':split,'source_row':str(position)})
    return rows,labels

def oracle(rows):
    import pandas as pd
    sets={side:{int(r['subject_id']) for r in rows if r['split']==side} for side in ['train','test']}
    table=pd.crosstab(pd.Series([int(r['subject_id']) for r in rows],name='subject_id'),pd.Series([r['split'] for r in rows],name='split'))
    for column in ['train','test']:
        if column not in table: table[column]=0
    shared_table=sorted(int(i) for i,r in table.iterrows() if r['train']>0 and r['test']>0)
    shared_set=sorted(sets['train'] & sets['test'])
    assert shared_set==shared_table
    return {'n_records':len(rows),'n_train_rows':sum(r['split']=='train' for r in rows),
        'n_test_rows':sum(r['split']=='test' for r in rows),'train_subjects':sorted(sets['train']),
        'test_subjects':sorted(sets['test']),'overlapping_subjects_set_oracle':shared_set,
        'overlapping_subjects_crosstab_oracle':shared_table,'oracles_agree':True,
        'n_activities':len({r['activity_id'] for r in rows}),
        'unit_boundary':'Rows are originally windowed repeated measurements; participants are supplied groups, not independent new collections.'}

def prepared_outputs():
    import numpy as np, pandas as pd, sklearn
    from sklearn.model_selection import ShuffleSplit
    rows,labels=rows_from_metadata()
    fields=list(rows[0])
    save_csv('har_official_manifest.csv',rows,fields)
    original=oracle(rows)
    assert original['n_records']==10299 and original['n_train_rows']==7352 and original['n_test_rows']==2947
    assert len(original['train_subjects'])==21 and len(original['test_subjects'])==9
    assert not original['overlapping_subjects_set_oracle']
    original_train=[dict(r) for r in rows if r['split']=='train']
    train_idx,test_idx=next(ShuffleSplit(n_splits=1,test_size=0.30,random_state=SEED).split(np.zeros(len(original_train))))
    test_set=set(int(i) for i in test_idx)
    shuffled=[dict(r,split='test' if i in test_set else 'train') for i,r in enumerate(original_train)]
    constructed=oracle(shuffled)
    assert constructed['overlapping_subjects_set_oracle'], 'Constructed fault must actually share subjects'
    save_csv('har_constructed_train_window_shuffle_manifest.csv',shuffled,fields)
    save_json('HAR_INDEPENDENT_METADATA_ORACLES.json',{'official':original,'constructed_original_train_only_shuffle':constructed,
        'construction':{'library':'actual sklearn ShuffleSplit','seed':SEED,'test_size':0.30,'uses_original_test_windows':False,
            'label':'Our explicit fault example, not the original UCI split or a classification experiment'},
        'versions':{'numpy':np.__version__,'pandas':pd.__version__,'scikit-learn':sklearn.__version__},
        'training_activity_counts':dict(sorted(Counter(r['label'] for r in original_train).items()))})
    unit_counts=[]
    for subject in range(1,31):
        member=[r for r in rows if int(r['subject_id'])==subject]
        unit_counts.append({'subject_id':subject,'official_split':member[0]['split'],'windows':len(member),'n_activities':len({r['activity_id'] for r in member})})
    save_csv('har_subject_unit_counts.csv',unit_counts,['subject_id','official_split','windows','n_activities'])
    return rows,shuffled,labels

def audit_rows(rows,shuffled,labels,freeze_path):
    # This phase is intentionally gated until corrected core source is frozen.
    freeze=json.loads(Path(freeze_path).read_text(encoding='utf-8'))
    expected=freeze.get('runtime_sha256') or freeze.get('core_source_sha256') or freeze.get('source_sha256')
    if not isinstance(expected,dict) or len(expected)!=8:
        raise ValueError('Runtime freeze must supply eight runtime/source SHA-256 entries.')
    src=PROJECT/'src'
    actual={f'src/episodeaudit/{p.name}':sha(p.read_bytes()) for p in sorted((src/'episodeaudit').glob('*.py'))}
    normalized={('src/episodeaudit/'+Path(k.replace('\\','/')).name):v for k,v in expected.items()}
    canonical=json.loads((PROJECT/'provenance/CANONICAL_RUNTIME_SHA256.json').read_text(encoding='utf-8'))
    assert actual==normalized==canonical,'Runtime has changed or freeze is not the approved corrected version'
    sys.path.insert(0,str(src))
    from episodeaudit import manifest_from_rows,audit_integrity,sample_indices,evaluate_predictions,__version__
    import numpy as np
    official=manifest_from_rows(rows)
    train=[r for r in rows if r['split']=='train']; test=[r for r in rows if r['split']=='test']
    members=[{'collection_id':r['collection_id'],'sample_id':r['sample_id']} for r in train]
    lineage={'allowed_source_collections':['UCI_HAR_240'],'stages':[
        {'name':'training_activity_frequency','purpose':'fit','fit_sample_ids':members},
        {'name':'constant_rule_selection','purpose':'model_selection','fit_sample_ids':members}]}
    save_json('har_train_only_lineage.json',lineage)
    audits={}
    for name,manifest,policy in [('official_unspecified',official,'unspecified'),('official_disjoint',official,'disjoint'),
        ('constructed_train_shuffle_disjoint',manifest_from_rows(shuffled),'disjoint'),('restored_official_disjoint',official,'disjoint')]:
        result=audit_integrity(manifest,group_policy=policy,lineage=lineage if name.startswith(('official','restored')) else None)
        audits[name]=result; save_json('results/'+name+'.json',result)
    assert audits['official_unspecified']['checks']['groups']['status']=='UNKNOWN'
    assert audits['official_disjoint']['checks']['groups']['status']=='PASS'
    assert audits['constructed_train_shuffle_disjoint']['checks']['groups']['status']=='FAIL'
    assert audits['restored_official_disjoint']['checks']['groups']['status']=='PASS'
    assert audits['official_disjoint']['checks']['declared_lineage']['status']=='PASS'
    # Isolate a label-using transform with a missing source member split.
    fault_rows=copy.deepcopy(rows); fault_rows[0]['split']=''
    transform_lineage={'allowed_source_collections':['UCI_HAR_240'],'stages':[{'name':'label_using_transform_probe',
        'purpose':'transform','sample_ids':[members[0]],'uses_labels':True}]}
    save_csv('har_fault_transform_missing_split_manifest.csv',fault_rows,list(fault_rows[0]))
    save_json('har_fault_transform_lineage.json',transform_lineage)
    fault=audit_integrity(manifest_from_rows(fault_rows),group_policy='disjoint',lineage=transform_lineage)
    save_json('results/fault_transform_missing_split.json',fault)
    assert fault['checks']['declared_lineage']['status']=='UNKNOWN','Missing transform split was incorrectly certified'
    # Exploratory post-run controls are declared in their separate dated plan.
    # The identical training-member declaration is now supplied with restored
    # official membership, then a genuine held-out member declares label access.
    repaired=audit_integrity(official,group_policy='disjoint',lineage=transform_lineage)
    save_json('results/repaired_transform_official_membership.json',repaired)
    assert repaired['checks']['declared_lineage']['status']=='PASS'
    heldout_member={'collection_id':test[0]['collection_id'],'sample_id':test[0]['sample_id']}
    heldout_lineage={'allowed_source_collections':['UCI_HAR_240'],'stages':[{
        'name':'heldout_label_using_transform_probe','purpose':'transform',
        'sample_ids':[heldout_member],'uses_labels':True}]}
    save_json('har_fault_heldout_label_transform_lineage.json',heldout_lineage)
    heldout=audit_integrity(official,group_policy='disjoint',lineage=heldout_lineage)
    save_json('results/heldout_label_using_transform.json',heldout)
    assert heldout['checks']['declared_lineage']['status']=='FAIL'
    assert any('evaluation_labels_used_in_transform_stage' in finding['reasons']
               for finding in heldout['checks']['declared_lineage']['findings'])
    exposure=[]
    training_manifest=manifest_from_rows(train)
    trace_oracles=[]
    by_member={(r['collection_id'],r['sample_id']):r for r in train}
    for strategy in ['image','group']:
        sampling=sample_indices(training_manifest,len(train),strategy=strategy,seed=SEED,image_replace=False)
        save_json('results/exposure_'+strategy+'.json',sampling)
        drawn=[tuple(member) for member in sampling['selected_members']]
        assert len(drawn)==len(train) and all(member in by_member for member in drawn)
        traced=Counter(by_member[member]['group_id'] for member in drawn)
        recorded={item['key'][-1]:item['n_draws'] for item in sampling['group_exposures']}
        assert dict(sorted(traced.items()))==dict(sorted(recorded.items()))
        if strategy=='image':
            assert len(set(drawn))==len(train)
            assert traced==Counter(r['group_id'] for r in train)
        trace_oracles.append({'strategy':strategy,'membership_recount_matches_exposure_report':True,
            'all_selected_members_are_official_training_rows':True,'n_draws':len(drawn),
            'n_unique_drawn_members':len(set(drawn)),
            'provided_subject_group_counts_recounted_from_members':dict(sorted(traced.items()))})
        exposure.append({'strategy':strategy,'draw_budget':len(train),'seed':SEED,
            'replacement':'without replacement full pass' if strategy=='image' else 'with replacement group draws',
            'result_file':'results/exposure_'+strategy+'.json','claim':'Allocation only; not matched model training or improved prediction.'})
    save_json('HAR_SAMPLING_MEMBERSHIP_ORACLES.json',trace_oracles)
    # Rule is determined only from official training labels, before any test metrics.
    counts=Counter(int(r['activity_id']) for r in train)
    chosen=min(counts,key=lambda activity:(-counts[activity],activity))
    rule={'type':'fixed training-majority constant','training_activity_counts':dict(sorted(counts.items())),
        'selected_activity_id':chosen,'selected_activity_label':labels[chosen],'tie_rule':'smallest activity ID',
        'rule_selection_input':'official train only','test_used_to_choose_rule':False}
    save_json('HAR_CONSTANT_RULE_FROZEN.json',rule)
    predictions=[{'sample_id':r['sample_id'],'collection_id':r['collection_id'],'y_true':r['label'],'y_pred':labels[chosen]} for r in test]
    save_csv('har_official_test_constant_predictions.csv',predictions,list(predictions[0]))
    metrics=evaluate_predictions(predictions,manifest=official,classes=[labels[i] for i in sorted(labels)],
        bootstrap=1000,seed=72011,unit='group',stratify=False)
    save_json('results/official_test_constant_metrics.json',metrics)
    # Metric-key inspection is recorded if the API schema evolves; no values repaired.
    ba=metrics.get('balanced_accuracy',metrics.get('metrics',{}).get('balanced_accuracy'))
    assert ba is not None and np.isclose(ba,1/6),'Constant six-class BA must be 1/6'
    from sklearn.metrics import balanced_accuracy_score,accuracy_score
    actual_labels=[r['label'] for r in test]
    constant_labels=[labels[chosen]]*len(test)
    sklearn_ba=float(balanced_accuracy_score(actual_labels,constant_labels))
    sklearn_accuracy=float(accuracy_score(actual_labels,constant_labels))
    assert np.isclose(ba,sklearn_ba) and np.isclose(metrics['metrics']['accuracy'],sklearn_accuracy)
    assert metrics['n_provided_groups']==9 and metrics['bootstrap']['n_units']==9
    assert all(len(group['true_label_counts'])==6 for group in metrics['group_metrics'])
    save_json('HAR_METRIC_INDEPENDENT_ORACLES.json',{'actual_sklearn_balanced_accuracy':sklearn_ba,
        'actual_sklearn_accuracy':sklearn_accuracy,'analytic_constant_six_class_balanced_accuracy':1/6,
        'episodeaudit_matches_sklearn_and_analytic_oracles':True,
        'test_subjects_contain_all_six_activities':True,
        'boundary':'A fixed constant-rule interface demonstration, not a sensor-feature classifier benchmark.'})
    for result in list(audits.values())+[fault,repaired,heldout]:
        assert result['identity_evidence']['status']=='UNKNOWN'
        assert result['execution_leakage']['status']=='UNKNOWN'
    summary={'phase':'SECOND_ROUND_HAR','separate_from_original_453_assertions':True,'runtime_freeze_sha256':sha(Path(freeze_path).read_bytes()),
        'runtime_source_sha256':actual,'episodeaudit_version':__version__,
        'application_script_sha256':sha(Path(__file__).read_bytes()),
        'official_download_provenance_sha256':sha((ROOT/'HAR_DOWNLOAD_PROVENANCE.json').read_bytes()),
        'official_counts':oracle(rows),'constructed_counts':oracle(shuffled),
        'group_statuses':{k:v['checks']['groups']['status'] for k,v in audits.items()},
        'official_declared_lineage':audits['official_disjoint']['checks']['declared_lineage']['status'],
        'fault_transform_declared_lineage':fault['checks']['declared_lineage']['status'],'exposure':exposure,
        'repaired_transform_declared_lineage':repaired['checks']['declared_lineage']['status'],
        'heldout_label_transform_declared_lineage':heldout['checks']['declared_lineage']['status'],
        'heldout_label_transform_finding_reasons':sorted({reason
            for finding in heldout['checks']['declared_lineage']['findings'] for reason in finding['reasons']}),
        'constant_rule':rule,'constant_balanced_accuracy':float(ba),'expected_balanced_accuracy':1/6,
        'constant_accuracy':metrics['metrics']['accuracy'],'independent_sklearn_metric_oracle_matches':True,
        'bootstrap_unit':'9 original test subjects, unstratified because groups contain mixed activities',
        'interpretation':'A metadata-only real non-image workflow application. No sensor model, third-party adoption, new field/pathology cohort or algorithm superiority claim.'}
    save_json('SECOND_ROUND_HAR_SUMMARY.json',summary)
    print(json.dumps({'phase':'audit','group_statuses':summary['group_statuses'],'fault':summary['fault_transform_declared_lineage'],'constant_BA':ba}))

def main():
    parser=argparse.ArgumentParser(description='Optional local HAR metadata application. Current UCI says CC BY 4.0, while the original archive prohibits commercial use. No HAR rows are bundled; review both notices before opting into your own permitted local use.')
    parser.add_argument('--prepare-only',action='store_true'); parser.add_argument('--audit',action='store_true')
    parser.add_argument('--runtime-freeze',default=str(PROJECT/'provenance/CORRECTIVE_FREEZE_20261007.json'))
    parser.add_argument('--from-local-archive',type=Path,help='Recorded official ZIP placed in the ignored replayed_results/har/source_cache directory.')
    parser.add_argument('--opt-in-upstream-data',action='store_true',help='Explicit opt-in to local downloading/processing after reviewing the upstream notice discrepancy.')
    args=parser.parse_args()
    if not args.opt_in_upstream_data:
        parser.error('No automatic HAR download or parsing. Review docs/HAR_REPRODUCTION_AND_RIGHTS.md, then explicitly add --opt-in-upstream-data only for your own permitted local use.')
    if not args.prepare_only and not args.audit:
        parser.error('Choose --prepare-only or --audit')
    if args.from_local_archive:
        prepare(args.from_local_archive)
    elif not (ROOT/'HAR_DOWNLOAD_PROVENANCE.json').exists():
        cache=ROOT/'source_cache'/'official_UCI_download.zip'
        if not cache.exists():
            subprocess.run([sys.executable,str(PROJECT/'scripts/download_har_local_source.py'),'--opt-in-upstream-data'],check=True)
        prepare(cache)
    # All source and row-level output stays below the ignored local replay tree.
    for item in json.loads((ROOT/'HAR_DOWNLOAD_PROVENANCE.json').read_text(encoding='utf-8'))['metadata_files']:
        assert sha((ROOT/item['local_file']).read_bytes())==item['sha256']
    rows,shuffled,labels=prepared_outputs()
    if args.prepare_only:
        print(json.dumps({'phase':'prepared_only','metadata_rows':len(rows),'no_core_audit_run':True}))
    if args.audit:
        audit_rows(rows,shuffled,labels,args.runtime_freeze)

if __name__=='__main__': main()
