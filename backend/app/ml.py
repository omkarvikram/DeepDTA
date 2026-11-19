"""Fail-closed inference against the supplied artifacts, never simulated results."""
import hashlib
import json
import re
import threading
from functools import lru_cache
import h5py
import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
from .config import BACKEND, MODEL_DIR, ROOT
from . import kiba_features, kiba_coverage, kiba_uncertainty
KIBA_DIR = BACKEND / "models/kiba_two_input"

SMILES_VOCAB = {token: i + 1 for i, token in enumerate(['#','(',')','.','1','2','3','4','5','6','7','8','9','=','Br','C','Cl','F','I','N','O','P','S'])}
PROTEIN_VOCAB = {aa: i + 1 for i, aa in enumerate('ACDEFGHIKLMNPQRSTVWXY')}
TOKEN_PATTERN = re.compile(r'\[[^\]]+\]|Br|Cl|Si|Se|Na|Ca|Li|Mg|Al|Fe|Zn|Cu|[A-Za-z]|\d|[().=#\-+/\\:@?*]')
FILES = {'davis': 'DeepDTA_Davis_model.h5', 'kiba': 'deepdta_kiba_model.h5'}
DISCLAIMER = 'Research screening estimate only; not an experimental measurement or medical recommendation. Affinity does not establish efficacy, safety, protein function, stability, or a binding pose.'
LOCK = threading.RLock()
class ModelUnavailable(Exception): pass

def clean_sequence(raw):
    lines = raw.strip().splitlines()
    headers = [i for i, line in enumerate(lines) if line.strip().startswith('>')]
    if len(headers) > 1 or (headers and headers[0] != 0):
        raise ValueError('Submit one protein sequence, not multiple FASTA records.')
    sequence = re.sub(r'\s+', '', ''.join(line for line in lines if not line.startswith('>'))).upper()
    if not sequence or len(sequence) > 1000:
        raise ValueError('Protein must contain 1–1000 residues. Longer inputs are rejected, never truncated.')
    unknown = set(sequence) - set(PROTEIN_VOCAB)
    if unknown: raise ValueError('Unsupported protein characters: ' + ', '.join(sorted(unknown)))
    return sequence

def molecule(smiles):
    smiles = smiles.strip()
    if not smiles or len(smiles) > 2000 or re.search(r'\s', smiles):
        raise ValueError('Enter one SMILES string without whitespace (maximum 2000 characters).')
    mol = Chem.MolFromSmiles(smiles)
    if mol is None: raise ValueError('Invalid SMILES: RDKit could not parse the molecular structure.')
    return mol

def descriptors(smiles):
    mol = molecule(smiles)
    mw, logp = Descriptors.MolWt(mol), Descriptors.MolLogP(mol)
    hbd, hba = Lipinski.NumHDonors(mol), Lipinski.NumHAcceptors(mol)
    return dict(molecular_weight=mw, logp=logp, hydrogen_bond_donors=hbd, hydrogen_bond_acceptors=hba,
                tpsa=rdMolDescriptors.CalcTPSA(mol), formula=rdMolDescriptors.CalcMolFormula(mol),
                lipinski_violations=sum([mw > 500, logp > 5, hbd > 5, hba > 10]))

def encode(smiles, sequence):
    molecule(smiles)
    tokens = TOKEN_PATTERN.findall(smiles)
    if ''.join(tokens) != smiles: raise ValueError('SMILES contains characters not represented by the Davis tokenizer.')
    unsupported = sorted(set(tokens) - set(SMILES_VOCAB))
    if unsupported:
        raise ValueError('Davis training vocabulary does not support these SMILES tokens: ' + ', '.join(unsupported) + '. Input was not converted or truncated.')
    if len(tokens) > 100: raise ValueError('Davis accepts at most 100 SMILES tokens; input was not truncated.')
    sequence = clean_sequence(sequence)
    drug = np.zeros((1,100), dtype=np.int32)
    protein = np.zeros((1,1000), dtype=np.int32)
    drug[0,:len(tokens)] = [SMILES_VOCAB[t] for t in tokens]
    protein[0,:len(sequence)] = [PROTEIN_VOCAB[t] for t in sequence]
    return drug, protein, sequence

@lru_cache(maxsize=2)
def inspect(dataset):
    if dataset == 'kiba': return inspect_kiba()
    from . import davis_ensemble
    if (davis_ensemble.DIRECTORY / 'metadata.json').exists():
        try: return davis_ensemble.inspect()
        except (ValueError, OSError, KeyError) as exc:
            return dict(dataset='davis', available=False, reason=str(exc))
    path = MODEL_DIR / FILES[dataset]
    if not path.exists(): return {'dataset': dataset, 'available': False, 'reason': f'Model artifact missing: {path.name}'}
    with h5py.File(path, 'r') as f:
        conf = json.loads(f.attrs['model_config'])['config']
        inputs = [dict(name=l['config']['name'], shape=l['config'].get('batch_shape', l['config'].get('batch_input_shape'))) for l in conf['layers'] if l['class_name'] == 'InputLayer']
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(dataset=dataset, filename=path.name, sha256=digest, inputs=inputs, available=False, metrics=None)
    if dataset == 'kiba':
        result['reason'] = 'The supplied KIBA artifact does not match the two-input training notebook. Its feature encoders and matching training code are missing. Inference is disabled rather than guessing inputs.'
    elif [i['shape'][1:] for i in inputs] != [[100],[1000]]:
        result['reason'] = 'Davis input shapes do not match its notebook; inference disabled.'
    else:
        result.update(available=True, scale='pKd', interpretation='pKd = -log10(Kd in mol/L). Higher scores indicate stronger predicted binding.', preprocessing='Davis.ipynb printed vocabularies; regex SMILES tokens; post-padding with 0; 100 drug tokens / 1000 residues; no truncation.', limitations='Training notebook used its test fold as validation during training. No independently verified holdout metrics or calibrated uncertainty are available. Vocabulary excludes aromatic lowercase SMILES and stereochemistry tokens.')
    return result

@lru_cache(maxsize=1)
def tensorflow_runtime():
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(2)
    return tf

@lru_cache(maxsize=1)
def davis_model():
    tf = tensorflow_runtime()
    try:
        model = tf.keras.models.load_model(MODEL_DIR / FILES['davis'], compile=False)
    except Exception as exc:
        raise ModelUnavailable('Davis artifact could not load; inspect the server log and model compatibility.') from exc
    if tuple(model.output_shape) != (None,1): raise ModelUnavailable('Unexpected Davis output shape.')
    return model

def predict(dataset, smiles, sequence):
    if dataset not in FILES: raise ValueError('Dataset must be davis or kiba.')
    info = inspect(dataset)
    if not info['available']: raise ModelUnavailable(info['reason'])
    smiles = smiles.strip()
    from . import davis_ensemble
    if dataset == 'davis' and (davis_ensemble.DIRECTORY / 'metadata.json').exists():
        with LOCK:
            score, sequence, warnings, components = davis_ensemble.predict(smiles, sequence)
        return dict(score=score, sequence=sequence, model_version=f"davis-sha256:{info['sha256']}",
            provenance={**info, 'descriptors': descriptors(smiles), 'disclaimer': DISCLAIMER,
                'warnings': warnings, 'component_predictions': components,
                'numerical_accuracy': {'status':'unavailable', 'reason':'These weights have dataset-level error measurements, but no independent calibration for a per-prediction accuracy percentage.'}})
    if dataset == 'kiba':
        drug, protein, sequence = kiba_features.encode(smiles, sequence)
    else:
        drug, protein, sequence = encode(smiles, sequence)
    with LOCK:
        model = kiba_model() if dataset == 'kiba' else davis_model()
        output = model([drug, protein], training=False).numpy()
    score = float(output.reshape(-1)[0])
    if not np.isfinite(score): raise ModelUnavailable('The model produced a non-finite output; nothing was saved.')
    provenance = {**info, 'descriptors': descriptors(smiles), 'disclaimer': DISCLAIMER,
                  'warnings': prediction_warnings(dataset, smiles, sequence, info)}
    if dataset == 'kiba':
        provenance['data_context'] = kiba_coverage.for_input(smiles, sequence)
        provenance['numerical_accuracy'] = kiba_uncertainty.for_prediction(
            score, smiles, sequence, provenance['data_context'], info['trained_max_lengths'])
    else:
        provenance['numerical_accuracy'] = {'status': 'unavailable', 'reason': 'The supplied Davis model lacks an independent, overlap-checked error dataset for calibration.'}
    return dict(score=score, sequence=sequence, model_version=f"{dataset}-sha256:{info['sha256']}",
                provenance=provenance)


def inspect_kiba():
    artifact, metadata = KIBA_DIR / 'model.keras', KIBA_DIR / 'metadata.json'
    if not artifact.exists() or not metadata.exists():
        return dict(dataset='kiba', available=False, reason='The replacement two-input KIBA model has not completed training and evaluation.')
    info = json.loads(metadata.read_text())
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if digest != info['sha256'] or info['feature_version'] != kiba_features.VERSION or info['feature_dimension'] != kiba_features.DIM:
        return dict(dataset='kiba', available=False, reason='KIBA artifact or preprocessing integrity check failed.')
    cold_path = ROOT / 'docs/KIBA_COLD_VALIDATION.json'
    cold = None
    if cold_path.is_file():
        audit = json.loads(cold_path.read_text())
        if audit.get('feature_version') == kiba_features.VERSION and all(
            audit.get('source_sha256', {}).get(name) == info['split_manifest']['source_sha256'].get(name)
            for name in ('ligands_can.txt', 'proteins.txt', 'kiba_binding_affinity_v2.txt')
        ):
            cold = {'purpose': audit['purpose'], 'limitations': audit['limitations'], 'results': audit['results']}
    calibration = kiba_uncertainty.calibration()
    limitations = info['limitations'].replace(
            'No cold-drug/protein validation, experimental validation, or calibrated uncertainty.',
            'The deployed weights lack cold-drug/protein or external experimental validation. A post-hoc numerical accuracy estimate applies only to familiar-input, new-pair KIBA predictions.' if calibration else
            'No cold-drug/protein validation, experimental validation, or calibrated uncertainty.').replace(
            'No cold-drug/protein validation,',
            'Separate cold-split benchmark models have been evaluated; the deployed weights have no cold-split evaluation,')
    return dict(dataset='kiba', available=True, filename=artifact.name, sha256=digest,
        inputs=[{'name': name, 'shape': [None, kiba_features.DIM]} for name in ['drug_smiles_features','protein_sequence_features']],
        architecture=info['architecture'], metrics=info['metrics'], cold_benchmarks=cold,
        test_exposure=kiba_coverage.summary(),
        external_validation={'status':'not_established', 'reason':'No independently sourced, overlap-checked experimental benchmark has been evaluated. ChEMBL lookups on selected predictions are literature comparisons, not external model validation.'}, scale='KIBA score',
        interpretation='Predicted score on the supplied KIBA dataset scale. Not Kd, pKd, nM, or a confidence percentage.',
        preprocessing=info['preprocessing'], limitations=limitations,
        numerical_accuracy_calibration={'status': 'available', 'tolerance_kiba': calibration['accuracy_tolerance_kiba'],
            'calibration_pairs': calibration['calibration_pairs'], 'audit_pairs': calibration['audit_pairs']}
            if calibration else {'status': 'unavailable'},
        trained_max_lengths=info['trained_max_lengths'], inference_limits=info['inference_limits'],
        sources=['New two-input KIBA model trained on supplied canonical SMILES and protein sequences.',
                 'Original training folds 2–5: training; fold 1: validation; supplied test fold: evaluation only.',
                 'Affinity source SHA-256: '+info['split_manifest']['source_sha256']['kiba_binding_affinity_v2.txt']])

@lru_cache(maxsize=1)
def kiba_model():
    info = inspect('kiba')
    if not info['available']: raise ModelUnavailable(info['reason'])
    tf = tensorflow_runtime()
    try:
        model = tf.keras.models.load_model(KIBA_DIR / 'model.keras', compile=False)
    except Exception as exc:
        raise ModelUnavailable('Two-input KIBA model could not load.') from exc
    if len(model.inputs) != 2 or any(tuple(i.shape)[1:] != (kiba_features.DIM,) for i in model.inputs) or tuple(model.output_shape) != (None,1):
        raise ModelUnavailable('Unexpected two-input KIBA architecture.')
    return model

def prediction_warnings(dataset, smiles, sequence, info):
    if dataset == 'davis':
        return ['No calibrated uncertainty or independent holdout evaluation available.'] + (['X residues represent unknown amino acids.'] if 'X' in sequence else [])
    warnings = ['The numerical accuracy estimate comes from supplied KIBA pair-level data, not independent experimental validation. It does not establish accuracy on unseen drugs or targets.',
                'Predictions depend on SMILES representation; prefer the supplied canonical representation.']
    maximum = info['trained_max_lengths']
    if len(smiles) > maximum['smiles'] or len(sequence) > maximum['protein']:
        warnings.append('Input length exceeds the training dataset range; this is extrapolation. No input was truncated.')
    return warnings
