"""Plot observed public-safe HAR states, without participant-level data."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'reported_results/HAR_APPLICATION_PUBLIC_SUMMARY.json'
OUT=ROOT/'figures'
report=json.loads(INPUT.read_text(encoding='utf-8'))
states={key:report['protocol_states'][key]['check_states']['groups'] for key in ['official_unspecified','official_disjoint','constructed_train_shuffle_disjoint','restored_official_disjoint']}
assert states=={'official_unspecified':'UNKNOWN','official_disjoint':'PASS',
    'constructed_train_shuffle_disjoint':'FAIL','restored_official_disjoint':'PASS'}
report['fault_transform_declared_lineage']=report['postrun_transform_controls']['missing_training_transform_split']
report['repaired_transform_declared_lineage']=report['postrun_transform_controls']['same_declaration_with_repaired_official_membership']
report['heldout_label_transform_declared_lineage']=report['postrun_transform_controls']['genuine_heldout_label_transform']
assert report['fault_transform_declared_lineage']=='UNKNOWN'
assert report['repaired_transform_declared_lineage']=='PASS'
assert report['heldout_label_transform_declared_lineage']=='FAIL'
colors={'PASS':'#0072B2','FAIL':'#D55E00','UNKNOWN':'#666666'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'ps.fonttype':42})
fig,ax=plt.subplots(figsize=(7.4,4.65))
ax.set_position([.015,.03,.97,.93]);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
ax.text(.01,.98,'HAR: one manifest, observed audit decisions',weight='bold',fontsize=12,va='top')
ax.text(.01,.91,'10,299 windows · 30 participants · official training/test participants: 21/9',fontsize=9,va='top')
rows=[
 ('Official split, task unspecified',states['official_unspecified'],'Group protocol'),
 ('Official participant-disjoint task',states['official_disjoint'],'Group protocol'),
 ('Constructed row-random training split',states['constructed_train_shuffle_disjoint'],'21 shared participants'),
 ('Restore the recorded official split',states['restored_official_disjoint'],'No shared participants'),
 ('Label-using transform: partition absent',report['fault_transform_declared_lineage'],'Declared lineage'),
 ('Restore its recorded training partition',report['repaired_transform_declared_lineage'],'Declared lineage'),
 ('Declare held-out labels in the transform',report['heldout_label_transform_declared_lineage'],'Declared lineage'),
]
boxes=[]
for i,(action,state,evidence) in enumerate(rows):
    y=.815-i*.103
    patch=FancyBboxPatch((.012,y-.038),.965,.075,boxstyle='round,pad=.007,rounding_size=.009',
                        ec=colors[state],fc='#F7F7F7',lw=.9)
    ax.add_patch(patch)
    a=ax.text(.035,y,action,ha='left',va='center',fontsize=8.7)
    b=ax.text(.735,y,evidence,ha='right',va='center',fontsize=8,color='#555555')
    c=ax.text(.947,y,state,ha='right',va='center',fontsize=9,weight='bold',color=colors[state])
    boxes.extend([(patch,text) for text in (a,b,c)])
ax.text(.50,.075,'Raw-file verification, identity truth and actual execution remain UNKNOWN.',
        ha='center',va='center',fontsize=8.5,color='#666666')
ax.text(.50,.016,'Observed metadata contracts; no sensor model or newly acquired participants.',
        ha='center',va='bottom',fontsize=8,color='#666666')
fig.canvas.draw();renderer=fig.canvas.get_renderer()
for patch,text in boxes:
    pb=patch.get_window_extent(renderer);tb=text.get_window_extent(renderer)
    assert tb.x0>=pb.x0 and tb.x1<=pb.x1 and tb.y0>=pb.y0 and tb.y1<=pb.y1,text.get_text()
OUT.mkdir(exist_ok=True)
for suffix in ('pdf','png'):
    fig.savefig(OUT/f'Figure_S1_HAR_Joined_Workflow.{suffix}',dpi=450,bbox_inches='tight',pad_inches=.09)
plt.close(fig)
(OUT/'HAR_FIGURE_PROVENANCE.json').write_text(json.dumps({
    'input_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),
    'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'record_level_data_in_plot':False,'observed_states':dict((a,b) for a,b,c in rows),
    'source_boundary':'Software outputs from public-source metadata; no HAR window-level data are redistributed.'},indent=2),encoding='utf-8')
print('Supplementary Figure S1 generated from observed software outputs.')
