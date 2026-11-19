#!/usr/bin/env python3
"""Reproducible CPU/GPU CNN experiments using the project's TensorFlow/Keras stack.
No uploaded notebook is executed and no pickle is deserialized. Test evaluation
is a separate command, after a validation-only selection manifest is frozen.
"""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
import argparse,csv,hashlib,io,json,re,sys,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
DEFAULT=ROOT/'research/model_tuning_20261111'
TOKEN=re.compile(r'\[[^\]]+\]|Br|Cl|Si|Se|Na|Ca|Li|Mg|Al|Fe|Zn|Cu|[A-Za-z]|\d|[().=#\-+/\\:@?*]')
CONFIGS={
 'baseline':dict(filters=[16,32,48],lr=.001),
 'lower_lr':dict(filters=[16,32,48],lr=.0003),
 'higher_lr':dict(filters=[16,32,48],lr=.003),
 'smaller_cnn':dict(filters=[8,16,24],lr=.001),
 'wider_cnn':dict(filters=[32,64,96],lr=.001),
 'full_sequence':dict(filters=[16,32,48],lr=.001,full=True,strides=[2,2,1]),
 'fixed_lr':dict(filters=[16,32,48],lr=.001,schedule=False),
 'ngram_baseline':dict(kind='ngram',filters=[],lr=.001,branch=[128,64],head=[128,64],dropout=.1,l2=0.,head_dropout_after=[0],clipnorm=None),
 'ngram_wider':dict(kind='ngram',filters=[],lr=.001,branch=[256,128],head=[256,128],dropout=.2,l2=1e-5),
 'ngram_lower_lr':dict(kind='ngram',filters=[],lr=.0003,branch=[128,64],head=[128,64],dropout=.1,l2=0.,head_dropout_after=[0],clipnorm=None),
}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,data):
 path=Path(path);temporary=path.with_name(path.name+'.tmp')
 temporary.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');temporary.replace(path)
def concordance(y,p):
 y,p=np.asarray(y),np.asarray(p)
 if len(y)!=len(p) or not np.all(np.isfinite(y)) or not np.all(np.isfinite(p)):raise ValueError('Finite equal-length arrays required')
 ranks=np.searchsorted(np.unique(p),p)+1;tree=np.zeros(int(ranks.max(initial=0))+2,np.int64)
 def prefix(i):
  n=0
  while i>0:n+=int(tree[i]);i-=i&-i
  return n
 order=np.argsort(y,kind='stable');seen=0;total=0;good=0.;start=0
 while start<len(y):
  end=start+1
  while end<len(y) and y[order[end]]==y[order[start]]:end+=1
  for idx in order[start:end]:
   r=int(ranks[idx]);less=prefix(r-1);good+=less+.5*(prefix(r)-less);total+=seen
  for idx in order[start:end]:
   r=int(ranks[idx])
   while r<len(tree):tree[r]+=1;r+=r&-r
  seen+=end-start;start=end
 return good/total if total else None

def metrics(y,p):
 y,p=np.asarray(y,dtype=float),np.asarray(p,dtype=float)
 mse=float(np.mean((y-p)**2))
 return dict(n=len(y),mse=mse,rmse=float(np.sqrt(mse)),mae=float(np.mean(np.abs(y-p))),concordance_index=concordance(y,p))

def combine_predictions(values,weights=None):
 return np.average(np.asarray(values,dtype=float),axis=0,weights=weights)

def prepare(archive,out,dataset):
 out.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(archive) as z:
  names=['ligands_can.txt','proteins.txt','folds/train_fold_setting1.txt','folds/test_fold_setting1.txt']
  matrix='kiba_binding_affinity_v2.txt' if dataset=='kiba' else 'drug-target_interaction_affinities_Kd__Davis_et_al.2011v1.txt'
  raw={n:z.read(n) for n in names+[matrix]}
 drugs=json.loads(raw[names[0]]);proteins=json.loads(raw[names[1]])
 a=np.loadtxt(io.BytesIO(raw[matrix]));assert a.shape==(len(drugs),len(proteins))
 rows,cols=np.where(np.isfinite(a));pairs=np.column_stack([rows,cols]).astype('int32');y=a[rows,cols].astype('float32')
 if dataset=='davis':
  if np.any(y<=0):raise ValueError('Nonpositive Kd')
  y=-np.log10(y/1e9)
 folds=json.loads(raw[names[2]]);test=np.array(json.loads(raw[names[3]]),dtype='int32')
 valid=np.array(folds[0],dtype='int32');train=np.concatenate(folds[1:]).astype('int32')
 all_idx=np.concatenate([train,valid,test]);assert len(np.unique(all_idx))==len(y) and np.array_equal(np.sort(all_idx),np.arange(len(y)))
 d=list(drugs.values());p=list(proteins.values());keys=[hashlib.sha256((d[i]+'\n'+p[j]).encode()).hexdigest() for i,j in pairs]
 dtokens=[TOKEN.findall(s) for s in d]
 if any(''.join(t)!=s for t,s in zip(dtokens,d)):raise ValueError('Tokenizer did not cover all characters')
 # Purge also the collisions created by the legacy 100/1000 crop. Use the same
 # conservative split for all architectures, including full-sequence models.
 split_keys=[hashlib.sha256((''.join(dtokens[i][:100])+'\n'+p[j][:1000]).encode()).hexdigest() for i,j in pairs]
 tkeys={split_keys[i] for i in test};vkeys={split_keys[i] for i in valid}-tkeys
 original=dict(train=len(train),validation=len(valid),test=len(test))
 heldout_keys=tkeys|vkeys
 train=np.array([i for i in train if split_keys[i] not in heldout_keys],dtype='int32');valid=np.array([i for i in valid if split_keys[i] not in tkeys],dtype='int32')
 # Only training input identities determine token vocabularies. Unknown != padding.
 dv={t:i+2 for i,t in enumerate(sorted({t for idx in np.unique(pairs[train,0]) for t in dtokens[idx]}))}
 pv={t:i+2 for i,t in enumerate(sorted({t for idx in np.unique(pairs[train,1]) for t in p[idx]}))}
 def encode(seqs,vocab):
  enc=np.zeros((len(seqs),max(map(len,seqs))),dtype='int32')
  for i,s in enumerate(seqs):enc[i,:len(s)]=[vocab.get(t,1) for t in s]
  return enc
 D,P=encode(dtokens,dv),encode(p,pv)
 save(out/'inputs.json',dict(drugs=d,proteins=p))
 np.savez_compressed(out/'prepared.npz',D=D,P=P,pairs=pairs,y_train=y[train],y_validation=y[valid],y_test=y[test],train=train,validation=valid,test=test,keys=np.array(keys))
 manifest=dict(dataset=dataset,archive_sha256=sha(archive),source_sha256={n:hashlib.sha256(b).hexdigest() for n,b in raw.items()},original_rows=original,rows=dict(train=len(train),validation=len(valid),test=len(test)),removed_for_exact_input_overlap=dict(train=original['train']-len(train),validation=original['validation']-len(valid)),scale='pKd' if dataset=='davis' else 'KIBA',drug_vocab=dv,protein_vocab=pv,padding_id=0,unknown_id=1,drug_ids=list(drugs),protein_ids=list(proteins),max_lengths=dict(drug_tokens=D.shape[1],protein_residues=P.shape[1]),split_policy='Supplied training folds 2-5 for fitting; fold 1 for selection; supplied test indices fixed. Purge training input-pair groups appearing in validation/test and validation groups appearing in test. Duplicate rows within test retained and identified.',test_limit='Pair-level benchmark, not independent external or cold-drug/protein validation. Historical notebook test results were already seen.',prepared_sha256=sha(out/'prepared.npz'))
 manifest['split_policy']+=' Also purge collisions after the legacy 100-drug-token/1000-residue crop; all trial families use this same conservative split.'
 manifest['inputs_sha256']=sha(out/'inputs.json')
 manifest['tokenizer_pattern']=TOKEN.pattern;manifest['target_dtype']=str(y.dtype)
 save(out/'manifest.json',manifest);print(json.dumps({k:manifest[k] for k in ['dataset','rows','removed_for_exact_input_overlap','max_lengths']},indent=2),flush=True)

def setup_tf(seed,threads):
 import tensorflow as tf
 try:
  tf.config.threading.set_intra_op_parallelism_threads(threads);tf.config.threading.set_inter_op_parallelism_threads(2)
 except RuntimeError:
  if tf.config.threading.get_intra_op_parallelism_threads()!=threads or tf.config.threading.get_inter_op_parallelism_threads()!=2:raise RuntimeError('Restart Python before changing TensorFlow thread settings')
 tf.keras.utils.set_random_seed(seed);tf.config.experimental.enable_op_determinism()
 return tf

def build_model(tf,D,P,config,mean,std,dv,pv):
 encoders=[];inputs=[];encoded=[]
 for name,values,vocab,kernel in [('drug',D,dv,4),('protein',P,pv,8)]:
  ngram=config.get('kind')=='ngram';reg=tf.keras.regularizers.l2(config.get('l2',1e-5))
  inp=tf.keras.Input((values.shape[1],),dtype='float32' if ngram else 'int32',name=name+('_features' if ngram else '_tokens'))
  if ngram:
   x=inp
   for units in config['branch']:x=tf.keras.layers.Dense(units,activation='relu',kernel_regularizer=reg)(x)
  else:
   x=tf.keras.layers.Embedding(len(vocab)+2,config.get('embedding_dim',32),name=name+'_embedding')(inp)
   strides=config.get('strides',[1]*len(config['filters']))
   if len(strides)!=len(config['filters']):raise ValueError('Specify one stride per convolution block')
   for i,(filters,stride) in enumerate(zip(config['filters'],strides)):
    x=tf.keras.layers.Conv1D(filters,kernel,strides=stride,padding='same',activation='relu',kernel_regularizer=reg,name=f'{name}_conv_{i+1}')(x)
   x=tf.keras.layers.GlobalMaxPooling1D()(x)
  enc=tf.keras.Model(inp,x,name=name+'_encoder');encoders.append(enc);inputs.append(inp);encoded.append(enc(inp))
 inp=tf.keras.Input((sum(e.output_shape[-1] for e in encoders),),name='paired_features')
 x=inp
 for i,units in enumerate(config.get('head',[256,128])):
  x=tf.keras.layers.Dense(units,activation='relu',kernel_regularizer=reg)(x)
  if i in config.get('head_dropout_after',[0,1]):x=tf.keras.layers.Dropout(config.get('dropout',.2))(x)
 x=tf.keras.layers.Dense(1)(x);x=tf.keras.layers.Rescaling(std,offset=mean)(x)
 head=tf.keras.Model(inp,x,name='affinity_head')
 model=tf.keras.Model(inputs,head(tf.keras.layers.Concatenate()(encoded)),name='two_input_affinity_'+('ngram' if ngram else 'cnn'))
 return model,*encoders,head

def predict_entities(tf,model,D,P,pairs,batch=64):
 enc=[]
 for name,values in [('drug',D),('protein',P)]:
  f=model.get_layer(name+'_encoder');enc.append(np.concatenate([f(values[i:i+batch],training=False).numpy() for i in range(0,len(values),batch)]))
 h=model.get_layer('affinity_head');out=[]
 for i in range(0,len(pairs),2048):
  q=pairs[i:i+2048];out.append(h(np.concatenate([enc[0][q[:,0]],enc[1][q[:,1]]],axis=1),training=False).numpy().ravel())
 return np.concatenate(out)

def inference_inputs(folder,a,config):
 """Reconstruct the exact training inputs for a frozen checkpoint."""
 if config.get('kind')=='ngram':
  sys.path.insert(0,str(ROOT/'backend'));from app.kiba_features import vector,VERSION
  if config.get('feature_version')!=VERSION:raise ValueError('Feature version mismatch')
  raw=json.loads((folder/'inputs.json').read_text())
  return np.stack([vector(s,'drug') for s in raw['drugs']]),np.stack([vector(s,'protein') for s in raw['proteins']])
 dl,pl=config['input_lengths'];return a['D'][:,:dl],a['P'][:,:pl]

def train(args):
 tf=setup_tf(args.seed,args.threads);folder=args.root/args.dataset;manifest=json.loads((folder/'manifest.json').read_text());a=np.load(folder/'prepared.npz')
 config=dict(embedding_dim=32,head=[256,128],dropout=.2,l2=1e-5)
 config.update(CONFIGS[args.config]);config.update(batch_size=args.batch,seed=args.seed,patience=args.patience,max_epochs=args.epochs)
 out=folder/'runs'/f'{args.config}_seed{args.seed}';out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists() and not args.resume:raise SystemExit('Run already complete; use --resume or a new seed.')
 D=a['D'];P=a['P'];D=D if config.get('full') else D[:,:100];P=P if config.get('full') else P[:,:1000]
 if config.get('kind')=='ngram':
  sys.path.insert(0,str(ROOT/'backend'));from app.kiba_features import vector,VERSION
  raw=json.loads((folder/'inputs.json').read_text());D=np.stack([vector(s,'drug') for s in raw['drugs']]);P=np.stack([vector(s,'protein') for s in raw['proteins']]);config['feature_version']=VERSION
 train_ids=a['train'];valid_ids=a['validation'];pairs=a['pairs'];yt=a['y_train'];yv=a['y_validation']
 model,de,pe,head=build_model(tf,D,P,config,float(yt.mean()),float(yt.std()),manifest['drug_vocab'],manifest['protein_vocab'])
 dropout_rng=[layer.seed_generator.state for layer in head.layers if isinstance(layer,tf.keras.layers.Dropout)]
 optimizer=tf.keras.optimizers.Adam(config['lr'],clipnorm=config.get('clipnorm',1.))
 optimizer.build(model.trainable_variables)
 checkpoint=tf.train.Checkpoint(model=model,optimizer=optimizer)
 state=dict(epoch=0,best_epoch=0,best_mse=1e10,wait=0,lr_wait=0,seconds=0.)
 if args.resume and (out/'state.json').exists():
  previous=json.loads((out/'config.json').read_text())
  for key in ['batch_size','seed','filters','lr','head','dropout','l2','kind','full','strides','branch','schedule','clipnorm','head_dropout_after','feature_version','prepared_sha256']:
   if previous.get(key)!=(manifest['prepared_sha256'] if key=='prepared_sha256' else config.get(key)):raise ValueError('Cannot resume a different configuration or dataset')
  state=json.loads((out/'state.json').read_text());checkpoint.restore(str(out/'last')).expect_partial()
  # Keras 3 dropout seed counters are not included in tf.train.Checkpoint.
  # Persist them explicitly. Older study checkpoints have exactly one dropout
  # draw per training batch, so their counters can be reconstructed exactly.
  for i,rng in enumerate(dropout_rng):
   value=state.get('dropout_rng',[v.numpy().tolist() for v in dropout_rng])[i]
   if 'dropout_rng' not in state:value[1]=state['epoch']*((len(yt)+args.batch-1)//args.batch)
   rng.assign(value)
 save(out/'config.json',{**config,'input_lengths':[D.shape[1],P.shape[1]],'parameters':model.count_params(),'prepared_sha256':manifest['prepared_sha256'],'tensorflow':tf.__version__,'cpu_intra_threads':args.threads,'cpu_inter_threads':2})
 D=tf.constant(D);P=tf.constant(P)
 @tf.function(input_signature=[tf.TensorSpec([None,2],tf.int32),tf.TensorSpec([None],tf.float32)])
 def step(ids,actual):
  # Same deterministic CNN calculation once per unique entity in the batch.
  # Dropout is only in the pair head, so every pair has its own dropout mask.
  ud,di=tf.unique(ids[:,0]);up,pi=tf.unique(ids[:,1])
  with tf.GradientTape() as tape:
   ed=de(tf.gather(D,ud),training=True);ep=pe(tf.gather(P,up),training=True)
   pred=tf.reshape(head(tf.concat([tf.gather(ed,di),tf.gather(ep,pi)],axis=1),training=True),[-1])
   mse=tf.reduce_mean(tf.square(actual-pred));loss=mse+tf.add_n(model.losses)
  gradients=tape.gradient(loss,model.trainable_variables);optimizer.apply_gradients(zip(gradients,model.trainable_variables))
  return mse
 history_path=out/'history.csv';start=time.monotonic()
 with history_path.open('a' if args.resume else 'w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=['epoch','learning_rate','training_loss_dropout','train_mse','validation_mse','validation_ci','generalization_gap','seconds'])
  if not args.resume:writer.writeheader()
  for epoch in range(state['epoch']+1,args.epochs+1):
   tick=time.monotonic();order=np.random.default_rng(args.seed+epoch).permutation(len(train_ids));loss=0.;lr=float(optimizer.learning_rate.numpy())
   for b in range(0,len(order),args.batch):
    idx=order[b:b+args.batch];loss+=float(step(pairs[train_ids[idx]],yt[idx]))*len(idx)
   both=predict_entities(tf,model,D,P,pairs[np.concatenate([train_ids,valid_ids])]);trpred,vp=both[:len(train_ids)],both[len(train_ids):]
   tm={'mse':float(np.mean((yt.astype(float)-trpred.astype(float))**2))};vm=metrics(yv,vp)
   row=dict(epoch=epoch,learning_rate=lr,training_loss_dropout=loss/len(yt),train_mse=tm['mse'],validation_mse=vm['mse'],validation_ci=vm['concordance_index'],generalization_gap=vm['mse']-tm['mse'],seconds=time.monotonic()-tick)
   writer.writerow(row);f.flush();print(json.dumps({'dataset':args.dataset,'config':args.config,**row}),flush=True)
   improved=vm['mse']<state['best_mse']-1e-5
   if improved:
    state.update(best_mse=vm['mse'],best_epoch=epoch,wait=0,lr_wait=0);model.save(out/'best.keras')
   else:state['wait']+=1;state['lr_wait']+=1
   if config.get('schedule',True) and state['lr_wait']>=4:
    optimizer.learning_rate.assign(max(float(optimizer.learning_rate.numpy())*.5,1e-5));state['lr_wait']=0
   state['epoch']=epoch;state['seconds']+=row['seconds'];state['dropout_rng']=[v.numpy().tolist() for v in dropout_rng];checkpoint.write(str(out/'last'));save(out/'state.json',state)
   if state['wait']>=args.patience:break
 best=tf.keras.models.load_model(out/'best.keras',compile=False)
 vp=predict_entities(tf,best,D,P,pairs[valid_ids]);tp=predict_entities(tf,best,D,P,pairs[train_ids])
 result=dict(dataset=args.dataset,config=args.config,seed=args.seed,epochs_completed=state['epoch'],best_epoch=state['best_epoch'],stopped_by='early_stopping' if state['wait']>=args.patience else 'epoch_limit',seconds=state['seconds'],parameters=best.count_params(),train=metrics(yt,tp),validation=metrics(yv,vp),model_sha256=sha(out/'best.keras'),configuration=config,input_lengths=[D.shape[1],P.shape[1]],test_evaluated=False)
 np.savez_compressed(out/'validation_predictions.npz',pair_index=valid_ids,actual=yv,predicted=vp)
 save(out/'result.json',result);print('RESULT '+json.dumps(result),flush=True)

def select(args):
 folder=args.root/args.dataset
 if (folder/'selection.json').exists():raise SystemExit('Selection already frozen; preserve the existing study.')
 manifest=json.loads((folder/'manifest.json').read_text())
 results=[]
 for path in sorted((folder/'runs').glob('*/result.json')):
  r=json.loads(path.read_text());config=json.loads((path.parent/'config.json').read_text());state=json.loads((path.parent/'state.json').read_text())
  if config['prepared_sha256']!=manifest['prepared_sha256']:raise ValueError('A trial used a different prepared dataset')
  if r['epochs_completed']!=state['epoch'] or r['configuration']['max_epochs']!=config['max_epochs']:raise ValueError('A trial is still running or has a stale result')
  if sha(path.parent/'best.keras')!=r['model_sha256']:raise ValueError('A trial checkpoint differs from its completed result')
  results.append((path,r))
 if not results:raise SystemExit('No completed trials')
 # Predeclared criterion: lowest validation MSE; CI and parameter count break ties.
 results.sort(key=lambda v:(v[1]['validation']['mse'],-(v[1]['validation']['concordance_index'] or 0),v[1]['parameters']))
 candidates=[]
 for path,r in results:
  candidates.append(dict(name=path.parent.name,runs=[path.parent.name],weights=[1.],model_sha256=[r['model_sha256']],config_sha256=[sha(path.parent/'config.json')],validation=r['validation'],parameters=r['parameters'],family='ngram' if r['config'].startswith('ngram') else 'cnn'))
 # A two-seed mean is considered only when both runs were selected/trained using
 # validation data. This averaging rule is declared before opening test labels.
 for path,r in results:
  other=folder/'runs'/f"{r['config']}_seed123"
  if r['seed']!=42 or not (other/'result.json').exists():continue
  s=json.loads((other/'result.json').read_text());x=np.load(path.parent/'validation_predictions.npz');z=np.load(other/'validation_predictions.npz')
  if not np.array_equal(x['pair_index'],z['pair_index']) or not np.array_equal(x['actual'],z['actual']):raise ValueError('Ensemble split mismatch')
  candidates.append(dict(name=r['config']+'_two_seed_mean',runs=[path.parent.name,other.name],weights=[.5,.5],model_sha256=[r['model_sha256'],s['model_sha256']],config_sha256=[sha(path.parent/'config.json'),sha(other/'config.json')],validation=metrics(x['actual'],combine_predictions([x['predicted'],z['predicted']])),parameters=r['parameters']+s['parameters'],family='ngram' if r['config'].startswith('ngram') else 'cnn'))
 candidates.sort(key=lambda r:(r['validation']['mse'],-r['validation']['concordance_index'],r['parameters']))
 # Exactly one predeclared cross-family blend: 50% best CNN, 50% best ngram.
 # No fitted weights and no mixing of Davis/KIBA scales.
 family_best=[next(c for c in candidates if c['family']==f) for f in ['cnn','ngram']]
 blend=dict(name='cnn_ngram_equal_blend',runs=[],weights=[],model_sha256=[],config_sha256=[],parameters=sum(c['parameters'] for c in family_best),family='hybrid')
 for candidate in family_best:
  for field in ['runs','model_sha256','config_sha256']:blend[field].extend(candidate[field])
  blend['weights'].extend([.5*w for w in candidate['weights']])
 predictions=[np.load(folder/'runs'/name/'validation_predictions.npz') for name in blend['runs']]
 blend['validation']=metrics(predictions[0]['actual'],combine_predictions([p['predicted'] for p in predictions],blend['weights']))
 candidates.append(blend);candidates.sort(key=lambda r:(r['validation']['mse'],-r['validation']['concordance_index'],r['parameters']))
 clean=np.load(folder/'feature_collision_masks.npz')['validation']
 for candidate in candidates:
  predictions=[np.load(folder/'runs'/name/'validation_predictions.npz') for name in candidate['runs']]
  candidate['feature_collision_free_validation']=metrics(predictions[0]['actual'][clean],combine_predictions([p['predicted'] for p in predictions],candidate['weights'])[clean])
 compare={name:next(c for c in candidates if c['name']==name) for name in ['baseline_seed42','ngram_baseline_seed42']}
 for family in ['cnn','ngram']:
  c=next(c for c in candidates if c['family']==family);compare[c['name']]=c
 compare[candidates[0]['name']]=candidates[0]
 manifest=json.loads((folder/'manifest.json').read_text())
 selected=dict(dataset=args.dataset,criterion='Minimum validation MSE; CI then parameter count as tie-breakers. No test metrics used.',selected_candidate=candidates[0]['name'],candidates=candidates,evaluation_candidates=list(compare.values()),prepared_sha256=manifest['prepared_sha256'],inputs_sha256=manifest['inputs_sha256'],manifest_sha256=sha(folder/'manifest.json'),ranking=[dict(run=p.parent.name,**r) for p,r in results])
 selected['frozen_at_utc']=datetime.now(timezone.utc).isoformat();selected['protocol_sha256']=sha(args.root/'protocol.json')
 selected['feature_collision_mask_sha256']=sha(folder/'feature_collision_masks.npz')
 selected['feature_implementation_sha256']=sha(ROOT/'backend/app/kiba_features.py')
 save(folder/'selection.json',selected);print(json.dumps(selected,indent=2))

def evaluate(args):
 tf=setup_tf(args.seed,args.threads);folder=args.root/args.dataset;sel=json.loads((folder/'selection.json').read_text())
 if (folder/'test_evaluation.json').exists():raise SystemExit('Test already evaluated. Preserve it; do not retune using test results.')
 if sha(folder/'manifest.json')!=sel['manifest_sha256']:raise ValueError('Preprocessing manifest changed')
 if sha(args.root/'protocol.json')!=sel['protocol_sha256']:raise ValueError('Frozen study protocol changed')
 if sha(folder/'feature_collision_masks.npz')!=sel['feature_collision_mask_sha256']:raise ValueError('Frozen sensitivity subset changed')
 if sha(ROOT/'backend/app/kiba_features.py')!=sel['feature_implementation_sha256']:raise ValueError('Frozen feature implementation changed')
 clean=np.load(folder/'feature_collision_masks.npz')['test']
 for name in ['prepared.npz','inputs.json']:
  if sha(folder/name)!=sel['prepared_sha256' if name.endswith('npz') else 'inputs_sha256']:raise ValueError('Frozen data changed')
 a=np.load(folder/'prepared.npz');ids=a['test'];pairs=a['pairs'][ids];actual=a['y_test'];cache={};scores=[]
 for candidate in sel['evaluation_candidates']:
  for name,expected,expected_config in zip(candidate['runs'],candidate['model_sha256'],candidate['config_sha256']):
   out=folder/'runs'/name
   if sha(out/'best.keras')!=expected:raise SystemExit('Selected model changed')
   if sha(out/'config.json')!=expected_config:raise SystemExit('Selected configuration changed')
   if name not in cache:
    model=tf.keras.models.load_model(out/'best.keras',compile=False);config=json.loads((out/'config.json').read_text());D,P=inference_inputs(folder,a,config)
    cache[name]=predict_entities(tf,model,D,P,pairs)
  pred=combine_predictions([cache[n] for n in candidate['runs']],candidate['weights'])
  scores.append(dict(**candidate,test=metrics(actual,pred),feature_collision_free_test=metrics(actual[clean],pred[clean])))
  with (folder/('test_predictions_'+candidate['name']+'.csv')).open('w',newline='') as f:
   w=csv.writer(f);w.writerow(['pair_index','input_pair_hash','actual','predicted']);w.writerows(zip(ids,a['keys'][ids],actual,pred))
 result=dict(dataset=args.dataset,selected_candidate=sel['selected_candidate'],selection_sha256=sha(folder/'selection.json'),comparisons=scores,training_mean_baseline=metrics(actual,np.full(len(actual),a['y_train'].mean())),note='Supplied pair-level test after exact/cropped input-pair purging. Historical test was exposed in supplied notebooks; this is not a new external benchmark. Candidates frozen on validation; test results must not be used to choose another winner.')
 save(folder/'test_evaluation.json',result);print(json.dumps(result,indent=2))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','train','select','evaluate']);p.add_argument('--dataset',choices=['davis','kiba'],required=True);p.add_argument('--archive',type=Path);p.add_argument('--root',type=Path,default=DEFAULT);p.add_argument('--config',choices=list(CONFIGS),default='baseline');p.add_argument('--epochs',type=int,default=80);p.add_argument('--patience',type=int,default=12);p.add_argument('--batch',type=int,default=1024);p.add_argument('--seed',type=int,default=42);p.add_argument('--threads',type=int,default=4);p.add_argument('--resume',action='store_true');args=p.parse_args()
 if args.command=='prepare':prepare(args.archive,args.root/args.dataset,args.dataset)
 elif args.command=='train':train(args)
 elif args.command=='select':select(args)
 else:evaluate(args)
if __name__=='__main__':main()
