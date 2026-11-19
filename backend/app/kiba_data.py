"""Read-only reference data. Recorded scores are never returned as predictions."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from .config import BACKEND, ROOT
from .security import current_user

DATA_DIR = Path(os.getenv('KIBA_DATA_DIR', str(BACKEND / 'data/kiba')))
FILES = ('kiba_binding_affinity_v2.txt', 'kiba_drug_sim.txt', 'kiba_target_sim.txt',
         'ligands_can.txt', 'ligands_iso.txt', 'proteins.txt',
         'test_fold_setting1.txt', 'train_fold_setting1.txt')

@lru_cache(maxsize=1)
def dataset():
    if not all((DATA_DIR / name).is_file() for name in FILES):
        raise HTTPException(503, 'KIBA reference files are missing. Configure KIBA_DATA_DIR.')
    read = lambda name: json.loads((DATA_DIR / name).read_text())
    drugs, iso, proteins = read('ligands_can.txt'), read('ligands_iso.txt'), read('proteins.txt')
    values = np.loadtxt(DATA_DIR / 'kiba_binding_affinity_v2.txt')
    if list(drugs) != list(iso) or values.shape != (len(drugs), len(proteins)):
        raise ValueError('KIBA identifier ordering or affinity matrix dimensions are inconsistent.')
    if np.isinf(values).any(): raise ValueError('KIBA contains infinite affinity values.')
    rows, cols = np.where(np.isfinite(values))
    folds, test = read('train_fold_setting1.txt'), read('test_fold_setting1.txt')
    indices = [i for fold in folds for i in fold] + test
    if any(type(i) is not int for i in indices) or sorted(indices) != list(range(len(rows))):
        raise ValueError('KIBA folds must partition all observed pairs exactly once.')
    splits = np.empty(len(rows), dtype=object)
    for n, fold in enumerate(folds): splits[fold] = f'train_fold_{n+1}'
    splits[test] = 'test'
    similarities = {}
    for name, size in [('kiba_drug_sim.txt', len(drugs)), ('kiba_target_sim.txt', len(proteins))]:
        matrix = np.loadtxt(DATA_DIR / name)
        if matrix.shape != (size, size) or not np.isfinite(matrix).all():
            raise ValueError(f'Invalid similarity matrix: {name}')
        similarities[name] = {'shape': list(matrix.shape), 'symmetric': bool(np.allclose(matrix, matrix.T)),
                              'minimum': float(matrix.min()), 'maximum': float(matrix.max())}
    metadata = dict(drugs=len(drugs), proteins=len(proteins), observed_pairs=len(rows),
        missing_pairs=int(np.isnan(values).sum()), train_pairs=sum(map(len, folds)), test_pairs=len(test),
        score_min=float(np.nanmin(values)), score_max=float(np.nanmax(values)), scale='KIBA score',
        kind='recorded_dataset_value', similarities=similarities,
        sha256={name: hashlib.sha256((DATA_DIR/name).read_bytes()).hexdigest() for name in FILES},
        ordering='JSON insertion order; fold indices into row-major finite entries of affinity matrix.',
        limitations='Reference dataset scores, not new predictions or independent biological validation. KIBA scores are not Kd, pKd or nM. Similarity-file identifiers are inferred from matching dimensions; matching training encoders are still required for the original five-input model.')
    return drugs, iso, proteins, values, rows, cols, splits, metadata

router = APIRouter(prefix='/api/kiba', tags=['KIBA reference data'], dependencies=[Depends(current_user)])

@router.get('/summary')
def summary(): return dataset()[-1]

@router.get('/records')
def records(drug: str=Query('', max_length=100), protein: str=Query('', max_length=100),
            split: str=Query('', pattern=r'^(|test|train|train_fold_[1-5])$'),
            offset: int=Query(0, ge=0), limit: int=Query(20, ge=1, le=100)):
    drugs, iso, proteins, values, rows, cols, splits, meta = dataset()
    drug_ids, protein_ids = list(drugs), list(proteins)
    drug_matches = np.array([drug.upper().strip() in x.upper() for x in drug_ids])
    protein_matches = np.array([protein.upper().strip() in x.upper() for x in protein_ids])
    mask = drug_matches[rows] & protein_matches[cols]
    if split == 'train': mask &= splits != 'test'
    elif split: mask &= splits == split
    selected = np.flatnonzero(mask)
    result = []
    for index in selected[offset:offset+limit]:
        r, c = int(rows[index]), int(cols[index])
        d, p = drug_ids[r], protein_ids[c]
        result.append(dict(pair_index=int(index), drug_id=d, protein_id=p, smiles=drugs[d],
            isomeric_smiles=iso[d], sequence=proteins[p], score=float(values[r,c]), split=str(splits[index]),
            kind='recorded_dataset_value', scale='KIBA score'))
    return {'total': len(selected), 'offset': offset, 'records': result,
            'source_sha256': meta['sha256']['kiba_binding_affinity_v2.txt']}

@router.get('/pair')
def pair(drug_id: str=Query(..., max_length=100), protein_id: str=Query(..., max_length=100)):
    drugs, iso, proteins, values, rows, cols, splits, meta = dataset()
    drug_id, protein_id = drug_id.strip().upper(), protein_id.strip().upper()
    if drug_id not in drugs or protein_id not in proteins: raise HTTPException(404, 'Identifier not found in KIBA.')
    r, c = list(drugs).index(drug_id), list(proteins).index(protein_id)
    if np.isnan(values[r,c]):
        return {'drug_id': drug_id, 'protein_id': protein_id, 'score': None, 'status': 'unmeasured',
                'message': 'No recorded KIBA value for this pair. Missing values are not zero.'}
    index = int(np.flatnonzero((rows == r) & (cols == c))[0])
    return dict(pair_index=index, drug_id=drug_id, protein_id=protein_id,
        smiles=drugs[drug_id], isomeric_smiles=iso[drug_id], sequence=proteins[protein_id],
        score=float(values[r,c]), split=str(splits[index]), kind='recorded_dataset_value', scale='KIBA score')
