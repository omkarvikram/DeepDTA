"""Deterministic, position-independent sequence features for the two-input KIBA model."""
import hashlib
import re
from functools import lru_cache
import numpy as np
from rdkit import Chem

DIM = 2048
VERSION = 'blake2b-ngram-logcounts-l2-v1'
AMINO_ACIDS = set('ACDEFGHIKLMNPQRSTVWY')

def sequence(raw):
    lines = raw.strip().splitlines()
    headers = [i for i, line in enumerate(lines) if line.strip().startswith('>')]
    if len(headers) > 1 or (headers and headers[0] != 0):
        raise ValueError('Submit one protein sequence, not multiple FASTA records.')
    value = re.sub(r'\s+', '', ''.join(line for line in lines if not line.strip().startswith('>'))).upper()
    if not value or len(value) > 10000 or set(value) - AMINO_ACIDS:
        raise ValueError('KIBA requires 1–10000 standard amino-acid residues; unknown residues are unsupported.')
    return value

def smiles(raw):
    value = raw.strip()
    if not value or len(value) > 2000 or re.search(r'\s', value):
        raise ValueError('KIBA requires one SMILES string of at most 2000 characters without whitespace.')
    if Chem.MolFromSmiles(value) is None: raise ValueError('Invalid SMILES: RDKit could not parse the molecular structure.')
    return value

@lru_cache(maxsize=512)
def vector(value, kind):
    """All characters contribute; no padding, truncation, vocabulary fitting or label access."""
    result = np.zeros(DIM, dtype=np.float32)
    for size in range(1, (4 if kind == 'drug' else 3) + 1):
        for start in range(len(value) - size + 1):
            token = value[start:start+size].encode('utf-8')
            index = int.from_bytes(hashlib.blake2b(token, digest_size=8, person=b'kiba-v1').digest(), 'little') % (DIM-1)
            result[index] += 1
    np.log1p(result, out=result)
    norm = np.linalg.norm(result)
    if norm: result /= norm
    result[-1] = np.log1p(len(value)) / 10.0
    result.flags.writeable = False
    return result

def encode(raw_smiles, raw_sequence):
    drug, protein = smiles(raw_smiles), sequence(raw_sequence)
    return vector(drug, 'drug')[None,:], vector(protein, 'protein')[None,:], protein
