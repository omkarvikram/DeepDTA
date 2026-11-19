"""Use the validation-selected research model with its own saved preprocessing.
This intentionally does not change the website's deployed model or calibration.
"""
import argparse,json,re,sys
from pathlib import Path
import numpy as np
from tune_affinity_cnn import DEFAULT,ROOT,sha,setup_tf,combine_predictions

class ResearchPredictor:
 def __init__(self,dataset,root=DEFAULT,threads=2,candidate_name=None,family=None):
  self.tf=setup_tf(42,threads);self.folder=Path(root)/dataset
  self.manifest=json.loads((self.folder/'manifest.json').read_text())
  self.tokenizer=re.compile(self.manifest['tokenizer_pattern'])
  selection=json.loads((self.folder/'selection.json').read_text())
  if sha(self.folder/'manifest.json')!=selection['manifest_sha256']:raise ValueError('Preprocessing manifest checksum mismatch')
  if family:
   if family not in ['cnn','ngram'] or candidate_name:raise ValueError('Select a family or a candidate, not both')
   candidate_name=next(c['name'] for c in selection['candidates'] if c['family']==family)
  name=candidate_name or selection['selected_candidate']
  self.candidate=next((c for c in selection['candidates'] if c['name']==name),None)
  if self.candidate is None:raise ValueError('Candidate is not in the frozen study selection')
  if self.candidate['family']!='cnn' and sha(ROOT/'backend/app/kiba_features.py')!=selection['feature_implementation_sha256']:raise ValueError('Feature implementation checksum mismatch')
  self.models=[]
  for run,expected,config_sha in zip(self.candidate['runs'],self.candidate['model_sha256'],self.candidate['config_sha256']):
   folder=self.folder/'runs'/run
   if sha(folder/'best.keras')!=expected:raise ValueError('Checkpoint checksum does not match frozen selection')
   if sha(folder/'config.json')!=config_sha:raise ValueError('Model configuration checksum mismatch')
   config=json.loads((folder/'config.json').read_text())
   self.models.append((self.tf.keras.models.load_model(folder/'best.keras',compile=False),config))
 def predict(self,smiles,protein):
  from rdkit import Chem
  lines=protein.strip().splitlines()
  if sum(line.strip().startswith('>') for line in lines)>1:raise ValueError('Provide one protein sequence, not multiple FASTA records')
  smiles=smiles.strip();protein=''.join(line.strip() for line in lines if not line.strip().startswith('>')).upper()
  if not smiles or Chem.MolFromSmiles(smiles) is None:raise ValueError('A valid SMILES string is required')
  if not protein or not protein.isalpha():raise ValueError('A protein amino-acid sequence is required')
  dt=self.tokenizer.findall(smiles)
  if any(c.get('kind')!='ngram' for _,c in self.models) and ''.join(dt)!=smiles:raise ValueError('Unsupported characters in SMILES for the CNN tokenizer')
  warnings=[];values=[]
  for model,config in self.models:
   if config.get('kind')=='ngram':
    sys.path.insert(0,str(ROOT/'backend'));from app.kiba_features import vector,VERSION
    if config['feature_version']!=VERSION:raise ValueError('Feature version mismatch')
    inputs=[vector(smiles,'drug')[None,:],vector(protein,'protein')[None,:]]
   else:
    inputs=[]
    for name,tokens,length in zip(['drug','protein'],[dt,list(protein)],config['input_lengths']):
     vocab=self.manifest[name+'_vocab'];arr=np.zeros((1,length),np.int32)
     arr[0,:min(len(tokens),length)]=[vocab.get(token,1) for token in tokens[:length]]
     if len(tokens)>length:warnings.append(f'{name}: {len(tokens)-length} tokens beyond the trained input length were truncated.')
     unknown=sum(token not in vocab for token in tokens[:length])
     if unknown:warnings.append(f'{name}: {unknown} tokens were not present in the training vocabulary.')
     inputs.append(arr)
   values.append(float(model(inputs,training=False).numpy().reshape(-1)[0]))
  return dict(prediction=float(combine_predictions(values,self.candidate['weights'])),scale=self.manifest['scale'],candidate=self.candidate['name'],component_predictions=values,component_weights=self.candidate['weights'],warnings=list(dict.fromkeys(warnings)),interpretation='Research screening estimate. Validation MSE/CI are population metrics, not an accuracy probability for this input. Independent exact-pair experimental validation remains necessary.')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',choices=['davis','kiba'],required=True);p.add_argument('--root',type=Path,default=DEFAULT);p.add_argument('--smiles',required=True);p.add_argument('--protein-file',type=Path,required=True);p.add_argument('--family',choices=['cnn','ngram'],help='Optionally restrict inference to the best validation-selected model in this family');args=p.parse_args()
 print(json.dumps(ResearchPredictor(args.dataset,args.root,family=args.family).predict(args.smiles,args.protein_file.read_text()),indent=2))
if __name__=='__main__':main()
