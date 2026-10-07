"""Reproduce the article artwork from deposited audit outputs, without image synthesis."""
from pathlib import Path
import csv, json, hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'reported_results'
OUT=ROOT/'figures'
OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,
                     'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,
                     'axes.titlesize':10,'axes.labelsize':9,'legend.fontsize':8,
                     'savefig.facecolor':'white','figure.facecolor':'white'})
BLUE='#0072B2'; ORANGE='#D55E00'; GREY='#666666'

def rows(name):
    with (R/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def save(fig,name):
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    for patch,text in getattr(fig,'audit_boxes',[]):
        pb=patch.get_window_extent(renderer);tb=text.get_window_extent(renderer)
        if tb.x0<pb.x0+1 or tb.x1>pb.x1-1 or tb.y0<pb.y0+1 or tb.y1>pb.y1-1:
            raise RuntimeError(f'Figure text exceeds its box: {name}: {text.get_text()}')
    fig.savefig(OUT/f'{name}.pdf',bbox_inches='tight',pad_inches=.09)
    fig.savefig(OUT/f'{name}.png',dpi=450,bbox_inches='tight',pad_inches=.09)
    plt.close(fig)

def box(ax,x,y,w,h,text,fc='#EDF4F8',ec=BLUE,fs=9):
    patch=FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.008,rounding_size=0.015',fc=fc,ec=ec,lw=1.0)
    ax.add_patch(patch)
    label=ax.text(x,y,text,ha='center',va='center',fontsize=fs,linespacing=1.25)
    if not hasattr(ax.figure,'audit_boxes'):ax.figure.audit_boxes=[]
    ax.figure.audit_boxes.append((patch,label))

def arrow(ax,start,end,color=GREY):
    ax.annotate('',xy=end,xytext=start,arrowprops={'arrowstyle':'-|>','color':color,'lw':1.0,
                 'shrinkA':4,'shrinkB':4})

fig,ax=plt.subplots(figsize=(7.2,4.2)); ax.set_position([.015,.035,.97,.93]);ax.set(xlim=(0,1),ylim=(0,1)); ax.axis('off')
ax.text(.01,.98,'Inputs with declared meanings',weight='bold',va='top',fontsize=11)
box(ax,.17,.80,.28,.16,'Manifest + stage declarations\nGroup kind and protocol\nSupplied digests / raw paths',fs=9)
box(ax,.50,.80,.28,.16,'Manifest + sampling settings\nEligible groups / draw budget\nReplacement mode and seed',fs=9)
box(ax,.83,.80,.28,.16,'Manifest + fixed predictions\nClass / probability schema\nDecision / resampling rule',fs=9)
box(ax,.17,.48,.28,.18,'Integrity and protocol\nMembers, groups and hashes\nDeclared fitting lineage',fs=9)
box(ax,.50,.48,.28,.18,'Exposure accounting\nAll eligible groups\nZero-draw groups retained',fs=9)
box(ax,.83,.48,.28,.18,'Prediction auditing\nClasses and probabilities\nExplicit resampling units',fs=9)
for x in [.17,.50,.83]: arrow(ax,(x,.71),(x,.58))
box(ax,.50,.16,.89,.15,'Manifest-linked JSON\nObserved findings, evidence basis and reproducible settings\nCheck-specific PASS / FAIL; absent provenance or intent stays UNKNOWN',fc='#F4F4F4',ec=GREY,fs=9)
for x in [.17,.50,.83]: arrow(ax,(x,.38),(x,.25))
ax.text(.50,.018,'Unobserved identity truth and actual execution are never certified by a metadata pass.',
        ha='center',va='bottom',fontsize=8.5,color=GREY)
save(fig,'Figure_1_Architecture')

classes=['healthy','septoria','stripe_rust']; w=rows('wheat_replay_class_metrics.csv')
fig,(a,b)=plt.subplots(1,2,figsize=(7.4,3.7),gridspec_kw={'width_ratios':[.93,1.1]})
a.axis('off'); a.set_title('A  COIL-20 protocol',loc='left',weight='bold',pad=14)
a.text(.02,.88,'Distinct bytes; shared object IDs.\nGroup-check status follows the task.',transform=a.transAxes,
       fontsize=8.5,va='top',linespacing=1.4)
for y,task,policy,state,color in [(.63,'New objects','disjoint','FAIL',ORANGE),
                                (.38,'Known objects,\nnew views','overlap_allowed','PASS',BLUE),
                                (.13,'Intent not stated','unspecified','UNKNOWN',GREY)]:
    a.add_patch(FancyBboxPatch((.02,y-.10),.94,.20,transform=a.transAxes,boxstyle='round,pad=0.01',
                              fc='#F7F7F7',ec=color,lw=1.1))
    a.text(.055,y+.025,task,transform=a.transAxes,fontsize=8.5,ha='left',va='center')
    a.text(.055,y-.062,policy,transform=a.transAxes,fontsize=8,color=GREY,ha='left',va='center')
    a.text(.91,y,state,transform=a.transAxes,color=color,weight='bold',ha='right',va='center',fontsize=9)
x=np.arange(3); width=.34
for offset,direction,color in [(-width/2,'JIC→Holeta',BLUE),(width/2,'Holeta→JIC',ORANGE)]:
    subset={r['class']:r for r in w if r['direction']==direction}
    vals=[float(subset[k]['recall']) for k in classes]
    b.bar(x+offset,vals,width,color=color,label=f'{direction}; BA={float(subset[classes[0]]["balanced_accuracy"]):.4f}')
b.set(xticks=x,xticklabels=['Healthy','Septoria','Stripe rust'],ylim=(0,1.04),ylabel='Recall (fixed predictions)')
b.set_title('B  Wheat class recall',loc='left',weight='bold',pad=14)
b.legend(loc='upper right',frameon=False,fontsize=7.8)
b.annotate('0/348',xy=(1+width/2,.003),xytext=(1.23,.14),fontsize=9,color=ORANGE,
           arrowprops={'arrowstyle':'->','color':ORANGE})
b.yaxis.grid(True,alpha=.16); b.set_axisbelow(True)
fig.subplots_adjust(wspace=.27,bottom=.14,top=.85)
save(fig,'Figure_2_Protocol_and_Class_Failure')

zero=next(r for r in rows('sampling_oracle_results.csv') if r['strategy']=='group' and int(r['budget'])==1)
counts=[int(zero[f'group_{i}_draws']) for i in range(4)]
u=rows('wheat_U0_software_sampling_replay.csv')
image=next(r for r in u if r['strategy']=='image')
episode=[r for r in u if r['strategy']=='episode']
fig,(a,b)=plt.subplots(1,2,figsize=(7.4,3.25))
a.bar(np.arange(4),counts,color=[BLUE if v else '#B3B3B3' for v in counts])
a.set(xticks=range(4),xticklabels=['g1','g2','g3','g4'],ylim=(0,1.40),ylabel='Draw count')
a.set_title('A  Four groups, one draw',loc='left',weight='bold')
a.text(.98,.96,'All four groups: CV=√3\nSelected group only: CV=0',transform=a.transAxes,fontsize=8.5,
       ha='right',va='top',linespacing=1.4,bbox={'facecolor':'white','edgecolor':'none','alpha':.9})
b.bar(range(4),[float(image['CV_including_zeros'])]+[float(r['CV_including_zeros']) for r in episode],
      color=[GREY]+[BLUE]*3)
b.set(xticks=range(4),xticklabels=['Image\nfull pass','Group\nseed 1','Group\nseed 2','Group\nseed 3'],
      ylim=(0,1.12),ylabel='Exposure CV across 2,200 episodes')
for i,val in enumerate([float(image['CV_including_zeros'])]+[float(r['CV_including_zeros']) for r in episode]):
    b.text(i,val+.027,f'{val:.4f}',ha='center',fontsize=8.5)
b.set_title('B  U0: equal draw budgets',loc='left',weight='bold')
for ax in [a,b]: ax.yaxis.grid(True,alpha=.16);ax.set_axisbelow(True)
fig.subplots_adjust(wspace=.35,bottom=.20,top=.84)
save(fig,'Figure_3_Exposure_Accounting')

fig,ax=plt.subplots(figsize=(13.28,5.31)); ax.set(xlim=(0,1),ylim=(0,1)); ax.axis('off')
ax.text(.5,.91,'EpisodeAudit',ha='center',weight='bold',fontsize=24)
ax.text(.5,.81,'Evidence-aware evaluation of grouped records',ha='center',fontsize=17)
labels=['Manifest and\nprovenance','Declared task\nand fitting members','Exposure and\nprediction reports']
for x,label in zip([.18,.5,.82],labels): box(ax,x,.55,.26,.25,label,fs=15)
arrow(ax,(.315,.55),(.365,.55));arrow(ax,(.635,.55),(.685,.55))
box(ax,.5,.19,.83,.15,'Observed violations are located. Missing evidence remains UNKNOWN.',fc='#F4F4F4',ec=GREY,fs=15)
save(fig,'Graphical_Abstract')

dependencies={'numpy':np.__version__,'matplotlib':matplotlib.__version__}
inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'wheat_replay_class_metrics.csv',R/'sampling_oracle_results.csv',R/'wheat_U0_software_sampling_replay.csv']}
receipt={'figures':4,'primary_article_figures':3,'source':'deterministic matplotlib from deposited audit outputs and explicitly illustrative software diagrams',
         'dependencies':dependencies,'input_hashes':inputs,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'no_synthesized_field_images':True,'U0_replacement_settings_disclosed':True}
(OUT/'FIGURE_PROVENANCE.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False))
