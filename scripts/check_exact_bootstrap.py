"""An exact finite oracle for the group-bootstrap contract.

The reference enumerates complete confusion-count tables using rational
arithmetic. It never invokes EpisodeAudit to construct expected results.
This is local software verification, not a population-coverage experiment.
"""
from pathlib import Path
from collections import Counter
from fractions import Fraction
from itertools import product
import hashlib
import importlib.metadata
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'validation/exact_bootstrap'
OUT = ROOT / 'replayed_results/exact_bootstrap'
CORE = ROOT
N_REPLICATES = 20000
SEED = 27017

CASES = [
    {'name': 'unequal_homogeneous_groups_unstratified', 'stratify': False,
     'groups': [[('A','A'),('A','A')], [('A','B')], [('B','B'),('B','A')]],
     'classes': ['A','B']},
    {'name': 'unequal_homogeneous_groups_stratified', 'stratify': True,
     'groups': [[('A','A'),('A','A')], [('A','B')], [('B','B'),('B','A')]],
     'classes': ['A','B']},
    {'name': 'mixed_label_groups_unstratified', 'stratify': False,
     'groups': [[('A','A'),('B','A')], [('A','B'),('B','B')],
                [('A','A'),('B','B'),('B','B')]], 'classes': ['A','B']},
    {'name': 'predicted_class_absent_from_truth', 'stratify': False,
     'groups': [[('A','A'),('A','A')], [('A','C')], [('B','B'),('B','A')]],
     'classes': ['A','B','C']},
]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def oracle_stats(rows):
    truth = Counter(a for a,b in rows)
    predicted = Counter(b for a,b in rows)
    diagonal = Counter(a for a,b in rows if a == b)
    labels = sorted(truth)
    return {
        'accuracy': Fraction(sum(diagonal.values()), len(rows)),
        'balanced_accuracy': sum((Fraction(diagonal[a],truth[a]) for a in labels), Fraction()) / len(labels),
        'macro_f1_observed_truth_classes': sum((Fraction(2*diagonal[a],truth[a]+predicted[a]) for a in labels), Fraction()) / len(labels),
    }

def enumerate_reference(case):
    groups = case['groups']
    original_truth = {a for group in groups for a,b in group}
    if case['stratify']:
        strata = {}
        for i,group in enumerate(groups):
            labels = {a for a,b in group}
            if len(labels) != 1:
                raise ValueError('The reference refuses to split a mixed group.')
            strata.setdefault(next(iter(labels)), []).append(i)
        choices = [list(product(indices,repeat=len(indices))) for label,indices in sorted(strata.items())]
        selections = [tuple(i for block in blocks for i in block) for blocks in product(*choices)]
    else:
        selections = list(product(range(len(groups)), repeat=len(groups)))
    values = {k: [] for k in oracle_stats([r for g in groups for r in g])}
    incomplete = 0
    for selection in selections:
        rows = [r for i in selection for r in groups[i]]
        metrics = oracle_stats(rows)
        values['accuracy'].append(metrics['accuracy'])
        if {a for a,b in rows} != original_truth:
            incomplete += 1
        else:
            for name in ('balanced_accuracy','macro_f1_observed_truth_classes'):
                values[name].append(metrics[name])
    def discrete_quantile(items, q):
        # Inverse-CDF of the finite, exactly equiprobable reference distribution.
        return sorted(items)[math.ceil(q*len(items))-1]
    return {
        'n_ordered_equiprobable_resamples': len(selections),
        'n_missing_truth_class_resamples': incomplete,
        'missing_truth_class_probability_exact': str(Fraction(incomplete,len(selections))),
        'point_metrics_exact': {k:str(v) for k,v in oracle_stats([r for g in groups for r in g]).items()},
        'conditional_distributions': {
            name: {'n_reference_resamples': len(items),
                   'exact_support_counts': {str(value):count for value,count in sorted(Counter(items).items())},
                   'lower_0_025': float(discrete_quantile(items,0.025)),
                   'upper_0_975': float(discrete_quantile(items,0.975))}
            for name,items in values.items()
        },
    }

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if '--prepare' in sys.argv:
        plan = {
            'status': 'SAVED_BEFORE_THIS_EXACT_ORACLE_RUN; post-initial-validation addendum',
            'date': '2026-10-07', 'cases': CASES,
            'n_monte_carlo_replicates_per_case': N_REPLICATES, 'seed': SEED,
            'point_metric_tolerance': 1e-12, 'interval_endpoint_tolerance': 1e-12,
            'missing_class_fraction_tolerance': 0.02,
            'reference_method': 'Exact ordered whole-group resample enumeration and Fraction confusion counts; inverse-CDF endpoints.',
            'limitations': ['Checks these finite fixed-prediction distributions, not general confidence-interval coverage.',
                'Monte Carlo endpoint equality is prechecked against discrete support; endpoints at probability jumps can vary in other examples.',
                'This assistant-generated local oracle is not external-laboratory replication.']}
        (OUT/'EXACT_ORACLE_PLAN.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Plan saved before implementation execution.')
        return
    if not (REFERENCE/'EXACT_ORACLE_PLAN.json').exists():
        raise RuntimeError('Save the oracle plan before running the implementation.')
    sys.path.insert(0,str(CORE/'src'))
    from episodeaudit import evaluate_predictions
    from episodeaudit.manifest import manifest_from_rows
    checks = []
    results = []
    for case in CASES:
        reference = enumerate_reference(case)
        manifest_rows = []
        predictions = []
        for g,group in enumerate(case['groups']):
            for j,(actual,predicted) in enumerate(group):
                sample = f'g{g}-r{j}'
                manifest_rows.append({'sample_id':sample,'collection_id':'finite-oracle',
                    'group_id':f'g{g}','group_kind':'other','label':actual})
                predictions.append({'sample_id':sample,'collection_id':'finite-oracle',
                    'y_true':actual,'y_pred':predicted})
        actual = evaluate_predictions(predictions,manifest=manifest_from_rows(manifest_rows),
            classes=case['classes'],bootstrap=N_REPLICATES,unit='group',
            stratify=case['stratify'],seed=SEED,confidence=0.95)
        for name,fraction in reference['point_metrics_exact'].items():
            checks.append({'case':case['name'],'property':'point:'+name,
                'passed':abs(actual['metrics'][name]-float(Fraction(fraction))) <= 1e-12})
        bootstrap = actual['bootstrap']
        p = float(Fraction(reference['missing_truth_class_probability_exact']))
        observed = bootstrap['n_replicates_missing_original_truth_classes']/N_REPLICATES
        checks.append({'case':case['name'],'property':'missing_class_fraction',
                       'passed':abs(observed-p)<=0.02,'exact':p,'observed':observed})
        checks.append({'case':case['name'],'property':'all_accuracy_replicates_retained',
                       'passed':bootstrap['intervals']['accuracy']['n_valid_replicates']==N_REPLICATES})
        for name,dist in reference['conditional_distributions'].items():
            interval = bootstrap['intervals'][name]
            for end,key in [('lower','lower_0_025'),('upper','upper_0_975')]:
                checks.append({'case':case['name'],'property':name+':'+end,
                    'passed':abs(interval[end]-dist[key])<=1e-12,
                    'exact':dist[key],'observed':interval[end]})
            if name != 'accuracy':
                checks.append({'case':case['name'],'property':name+':conditional_denominator',
                    'passed':interval['n_valid_replicates']==N_REPLICATES-bootstrap['n_replicates_missing_original_truth_classes']})
        if 'C' in case['classes']:
            c = next(row for row in actual['metrics']['per_class'] if row['label']=='C')
            checks.append({'case':case['name'],'property':'absent_truth_recall_undefined',
                           'passed':c['n_true']==0 and c['recall'] is None})
        (OUT/(case['name']+'.json')).write_text(json.dumps(actual,indent=2,allow_nan=False),encoding='utf-8')
        results.append({'case':case['name'],'reference':reference,'report_file':case['name']+'.json'})
    report = {'date':'2026-10-07','plan_sha256':sha(REFERENCE/'EXACT_ORACLE_PLAN.json'),
        'script_sha256':sha(Path(__file__)),
        'runtime_sha256':{p.name:sha(p) for p in sorted((CORE/'src/episodeaudit').glob('*.py'))},
        'python_version':sys.version.split()[0],'numpy_version':importlib.metadata.version('numpy'),
        'n_checks':len(checks),'n_failed':sum(not c['passed'] for c in checks),
        'n_real_observations':0,'n_synthetic_finite_distributions':len(CASES),
        'results':results,'checks':checks,
        'interpretation':'Finite-distribution implementation agreement only; does not establish frequentist coverage or specimen/collection independence.'}
    (OUT/'EXACT_ORACLE_REPLAY_RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'n_checks':report['n_checks'],'n_failed':report['n_failed']}))
    raise SystemExit(1 if report['n_failed'] else 0)

if __name__=='__main__':
    main()
