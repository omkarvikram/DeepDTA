"""Freeze validation-only selection, retrospectively evaluate once, export the Davis runtime."""
import json,shutil,csv
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from tune_affinity_cnn import ROOT,sha,metrics,combine_predictions,setup_tf,inference_inputs,predict_entities,save
OLD=ROOT/'research/model_tuning_20261111/davis'
NEW=ROOT/'research/davis_extension_20261111/davis'
OUT=ROOT/'backend/models/davis_optimized'

def member(folder,weight):
 c=json.loads((folder/'config.json').read_text());r=json.loads((folder/'result.json').read_text());state=json.loads((folder/'state.json').read_text())
 if state['epoch']!=r['epochs_completed'] or c['max_epochs']!=r['configuration']['max_epochs']:raise RuntimeError('Training is not complete: '+str(folder))
 if sha(folder/'best.keras')!=r['model_sha256']:raise RuntimeError('Checkpoint hash differs')
 return {'folder':str(folder.relative_to(ROOT)),'weight':weight,'sha256':r['model_sha256'],'config_sha256':sha(folder/'config.json'),'best_epoch':r['best_epoch'],'epochs_completed':r['epochs_completed'],'kind':c.get('kind','cnn'),'input_lengths':c['input_lengths']}

def candidate(name,members):
 arr=[np.load(ROOT/m['folder']/'validation_predictions.npz') for m in members]
 if any(not np.array_equal(arr[0]['pair_index'],a['pair_index']) for a in arr):raise ValueError('Validation rows differ')
 return {'name':name,'members':members,'validation':metrics(arr[0]['actual'],combine_predictions([a['predicted'] for a in arr],[m['weight'] for m in members]))}

def main():
 selection=NEW/'release_selection.json'; evaluation=NEW/'release_evaluation.json'
 if not selection.exists():
  ng=[member(OLD/'runs'/f'ngram_lower_lr_seed{seed}',.25) for seed in [42,123]]
  old=candidate('previous_hybrid',[member(OLD/'runs/higher_lr_seed42',.5),*ng])
  cnns=[candidate(name,[member(NEW/'runs'/name,1.)]) for name in ['higher_lr_seed42','full_sequence_seed42']]
  best=min(cnns,key=lambda c:(c['validation']['mse'],-c['validation']['concordance_index']))
  mix=candidate('extended_cnn_ngram_blend',[{**best['members'][0],'weight':.5},*ng])
  candidates=[old,*cnns,mix];winner=min(candidates,key=lambda c:(c['validation']['mse'],-c['validation']['concordance_index']))
  save(selection,{'frozen_utc':datetime.now(timezone.utc).isoformat(),'criterion':'Lowest validation MSE, CI tie-break. No new test result used.','winner':winner,'candidates':candidates,'protocol_sha256':sha(NEW.parent/'protocol.json'),'prepared_sha256':sha(NEW/'prepared.npz'),'manifest_sha256':sha(NEW/'manifest.json')})
 sel=json.loads(selection.read_text());winner=sel['winner']
 if sha(NEW/'prepared.npz')!=sel['prepared_sha256'] or sha(NEW.parent/'protocol.json')!=sel['protocol_sha256']:raise ValueError('Frozen release data or protocol changed')
 tf=setup_tf(42,2);a=np.load(NEW/'prepared.npz');raw=json.loads((NEW/'inputs.json').read_text());preds=[];vpreds=[]
 for m in winner['members']:
  folder=ROOT/m['folder']
  if sha(folder/'best.keras')!=m['sha256'] or sha(folder/'config.json')!=m['config_sha256']:raise ValueError('Frozen checkpoint changed')
  config=json.loads((folder/'config.json').read_text());D,P=inference_inputs(NEW,a,config)
  model=tf.keras.models.load_model(folder/'best.keras',compile=False)
  if not evaluation.exists():preds.append(predict_entities(tf,model,D,P,a['pairs'][a['test']]))
  vpreds.append(predict_entities(tf,model,D,P,a['pairs'][a['validation'][:12]]))
 if not evaluation.exists():
  predicted=combine_predictions(preds,[m['weight'] for m in winner['members']]);test=metrics(a['y_test'],predicted)
  oldeval=json.loads((OLD/'test_evaluation.json').read_text());previous=next(c['test'] for c in oldeval['comparisons'] if c['name']=='cnn_ngram_equal_blend');baseline=next(c['test'] for c in oldeval['comparisons'] if c['name']=='baseline_seed42')
  save(evaluation,{'selection_sha256':sha(selection),'selected':winner,'test':test,'previous_test':previous,'baseline_test':baseline,'note':'Retrospective benchmark on the previously inspected historical test. This is not a fresh blind test or independent external validation.'})
  with (NEW/'release_test_predictions.csv').open('w',newline='') as f:
   w=csv.writer(f);w.writerow(['pair_index','actual','predicted']);w.writerows(zip(a['test'],a['y_test'],predicted))
 result=json.loads(evaluation.read_text())
 if result['selection_sha256']!=sha(selection):raise ValueError('Frozen selection changed after evaluation')
 OUT.mkdir(parents=True,exist_ok=True);members=[];files={}
 for i,m in enumerate(winner['members']):
  filename=f'member_{i+1}.keras';shutil.copy2(ROOT/m['folder']/'best.keras',OUT/filename);files[filename]=sha(OUT/filename)
  members.append({k:v for k,v in {**m,'file':filename}.items() if k not in ['folder','sha256','config_sha256']})
 manifest=json.loads((NEW/'manifest.json').read_text())
 meta={'dataset':'davis','architecture':'Validation-selected ensemble of a sequence CNN and two hashed n-gram MLPs' if len(members)>1 else 'Sequence CNN',
  'members':members,'files':files,'feature_version':'blake2b-ngram-logcounts-l2-v1','feature_sha256':sha(ROOT/'backend/app/kiba_features.py'),
  'drug_vocab':manifest['drug_vocab'],'protein_vocab':manifest['protein_vocab'],'tokenizer_pattern':manifest['tokenizer_pattern'],
  'metrics':{'validation':winner['validation'],'test':result['test']},'selection':{'name':winner['name'],'criterion':sel['criterion'],'members':members},
  'benchmark_note':result['note'],'limitations':'Pair-level dataset evaluation. Familiar drugs and targets dominate. No independently calibrated per-prediction accuracy or clinical validation. CNN input cropping is disclosed.',
  'sources':['Supplied Davis Kd matrix, converted as pKd = 9 - log10(Kd in nM).','Training folds 2–5, validation fold 1, historical test fold. Exact and cropped input-pair overlaps purged.','Training pairs 17,272; validation pairs 4,383; benchmark pairs 5,010.','Base method: Öztürk et al., DeepDTA, Bioinformatics (2018), https://doi.org/10.1093/bioinformatics/bty593']}
 save(OUT/'metadata.json',meta)
 expected=combine_predictions(vpreds,[m['weight'] for m in winner['members']]);vectors=[]
 for idx,value in zip(a['validation'][:12],expected):
  d,p=a['pairs'][idx];vectors.append({'smiles':raw['drugs'][int(d)],'sequence':raw['proteins'][int(p)],'expected':float(value)})
 save(OUT/'parity_examples.json',vectors)
 save(ROOT/'docs/DAVIS_RELEASE_RESULTS.json',result)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
