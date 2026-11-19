"""Runtime-only Davis ensemble. Training and selection never run in the web server."""
import hashlib
import json
import re
from functools import lru_cache
import numpy as np
from .config import BACKEND
from . import kiba_features

DIRECTORY = BACKEND / 'models/davis_optimized'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

@lru_cache(maxsize=1)
def metadata():
    data = json.loads((DIRECTORY / 'metadata.json').read_text())
    for name, expected in data['files'].items():
        if digest(DIRECTORY / name) != expected:
            raise ValueError('Davis model integrity check failed: ' + name)
    if data['feature_version'] != kiba_features.VERSION or digest(BACKEND / 'app/kiba_features.py') != data['feature_sha256']:
        raise ValueError('Davis feature implementation differs from its training version.')
    weights = np.array([m['weight'] for m in data['members']], float)
    if np.any(weights < 0) or not np.isclose(weights.sum(), 1):
        raise ValueError('Invalid Davis ensemble weights.')
    return data

@lru_cache(maxsize=1)
def models():
    from .ml import tensorflow_runtime
    tf = tensorflow_runtime()
    return [tf.keras.models.load_model(DIRECTORY / m['file'], compile=False) for m in metadata()['members']]

def inspect():
    data = metadata()
    return dict(dataset='davis', available=True, filename='Davis validation-selected ensemble',
        sha256=digest(DIRECTORY / 'metadata.json'), inputs=[{'name':'drug_smiles'}, {'name':'protein_sequence'}],
        architecture=data['architecture'], scale='pKd', metrics=data['metrics'],
        interpretation='pKd = 9 - log10(Kd in nM). Higher pKd indicates stronger predicted binding.',
        preprocessing='Saved training vocabularies for the CNN and versioned hashed n-grams. Any CNN truncation is reported with the result.',
        limitations=data['limitations'], benchmark_note=data['benchmark_note'],
        external_validation={'status':'not_established','reason':'No independent external experimental benchmark or per-input accuracy calibration is established for these weights.'},
        sources=data['sources'], training_selection=data['selection'])

def predict(smiles, raw_sequence):
    from .ml import molecule
    molecule(smiles)
    lines=raw_sequence.strip().splitlines()
    headers=[i for i,line in enumerate(lines) if line.strip().startswith('>')]
    if len(headers)>1 or (headers and headers[0]!=0):
        raise ValueError('Submit one protein sequence or one FASTA record.')
    sequence=re.sub(r'\s+', '', ''.join(line for line in lines if not line.strip().startswith('>'))).upper()
    if not sequence or len(sequence)>10000 or set(sequence)-set('ACDEFGHIKLMNPQRSTVWXY'):
        raise ValueError('Protein must contain 1–10000 supported amino-acid residues.')
    data=metadata(); tokens=re.findall(data['tokenizer_pattern'],smiles)
    if ''.join(tokens)!=smiles:raise ValueError('Unsupported characters in the Davis SMILES tokenizer.')
    warnings=['Dataset MSE and concordance describe groups of predictions, not the accuracy probability of this pair.', data['benchmark_note']]
    predictions=[]
    for member,model in zip(data['members'],models()):
        if member['kind']=='ngram':
            inputs=[kiba_features.vector(smiles,'drug')[None,:],kiba_features.vector(sequence,'protein')[None,:]]
        else:
            inputs=[]
            for name,items,length in zip(['drug','protein'],[tokens,list(sequence)],member['input_lengths']):
                vocab=data[name+'_vocab']; values=np.zeros((1,length),np.int32)
                values[0,:min(length,len(items))]=[vocab.get(x,1) for x in items[:length]]
                if len(items)>length:
                    suffix=' The n-gram members use the full input.' if any(m['kind']=='ngram' for m in data['members']) else ''
                    warnings.append(f'CNN {name} input uses the first {length} of {len(items)} tokens.'+suffix)
                unknown=sum(x not in vocab for x in items[:length])
                if unknown:warnings.append(f'CNN {name} input contains {unknown} tokens absent from the training vocabulary.')
                inputs.append(values)
        predictions.append(float(model(inputs,training=False).numpy().reshape(-1)[0]))
    value=float(np.dot(np.array(predictions,dtype=np.float64),[m['weight'] for m in data['members']]))
    if not np.isfinite(value):raise ValueError('Davis produced a non-finite prediction.')
    return value,sequence,list(dict.fromkeys(warnings)),predictions
