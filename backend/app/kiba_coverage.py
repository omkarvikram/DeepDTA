"""Exact-input development exposure for the active KIBA weights.

This index contains hashes of inputs, never KIBA labels. It is not a chemical
similarity estimate, confidence interval, or independent validation result.
"""
import hashlib
import json
from functools import lru_cache

from .config import BACKEND, ROOT

INDEX = BACKEND / 'models/kiba_two_input/coverage_index.json'
METADATA = BACKEND / 'models/kiba_two_input/metadata.json'


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def pair_digest(smiles, sequence):
    return hashlib.sha256(smiles.encode('utf-8') + b'\0' + sequence.encode('utf-8')).hexdigest()


@lru_cache(maxsize=1)
def load_index():
    index = json.loads(INDEX.read_text())
    metadata = json.loads(METADATA.read_text())
    expected = metadata['split_manifest']['splits']
    if (index.get('format') != 'exact-input-exposure-v1' or
        index.get('model_sha256') != metadata['sha256'] or
        index.get('feature_version') != metadata['feature_version'] or
        any(index.get('split_sha256', {}).get(split) != expected[split]['sha256']
            for split in ('train', 'validation', 'test'))):
        raise ValueError('KIBA coverage index does not match the active model and data split.')
    return {
        'fit_drugs': frozenset(index['fit_drug_hashes']),
        'fit_proteins': frozenset(index['fit_protein_hashes']),
        'fit_pairs': frozenset(index['fit_pair_hashes']),
        'validation_pairs': frozenset(index['validation_pair_hashes']),
        'test_exposure': index['test_exposure'],
        'limitations': index['limitations'],
    }


def summary():
    try:
        index = load_index()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return {**index['test_exposure'], 'limitations': index['limitations']}


def for_input(smiles, sequence):
    try:
        index = load_index()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {'status': 'unavailable', 'explanation': 'Training-exposure index is unavailable or does not match this model.'}
    drug_seen = digest(smiles) in index['fit_drugs']
    protein_seen = digest(sequence) in index['fit_proteins']
    pair = pair_digest(smiles, sequence)
    pair_fit = pair in index['fit_pairs']
    pair_validation = pair in index['validation_pairs']
    if pair_fit:
        explanation = 'This exact SMILES and sequence pair appeared in fitting data. The prediction is not a new-pair test.'
    elif pair_validation:
        explanation = 'This exact pair appeared in model-selection data. It was not used to fit weights, but it is not untouched evaluation data.'
    elif drug_seen and protein_seen:
        explanation = 'This exact pair was not in fitting or model-selection data, but both exact inputs appeared separately in fitting data.'
    else:
        explanation = 'At least one exact input was absent from fitting data. The deployed model has no held-out test examples of unseen drugs or proteins.'
    return {'status': 'available', 'drug_seen_in_fit': drug_seen,
            'protein_seen_in_fit': protein_seen, 'pair_seen_in_fit': pair_fit,
            'pair_seen_in_validation': pair_validation, 'explanation': explanation,
            'limitations': index['limitations']}
