"""On-demand experimental evidence. Never treats KIBA scores as molar affinity."""
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from rdkit import Chem
from fastapi import HTTPException
from .search import fetch
from .config import ROOT
import json

BASE='https://www.ebi.ac.uk/chembl/api/data'

def structure(smiles):
    mol=Chem.MolFromSmiles(smiles)
    if mol is None: raise ValueError('Cannot verify compound structure.')
    return Chem.MolToSmiles(mol,isomericSmiles=True)

@lru_cache(maxsize=1)
def known_inputs():
    folder=ROOT/'data/kiba'
    if not folder.exists(): return {},{}
    drugs=json.loads((folder/'ligands_can.txt').read_text())
    proteins=json.loads((folder/'proteins.txt').read_text())
    return {structure(s):key for key,s in drugs.items()}, {s:key for key,s in proteins.items()}

def resolve(prediction, compound_id, accession):
    drugs,proteins=known_inputs()
    compound_id=(compound_id or drugs.get(structure(prediction.smiles)) or '').strip().upper()
    accession=(accession or proteins.get(prediction.sequence) or '').strip().upper()
    if not compound_id or not accession:
        raise HTTPException(422,'Enter a ChEMBL compound ID and UniProt accession. Automatic matching is available for supplied KIBA structures and sequences.')
    if not re.fullmatch(r'CHEMBL\d+',compound_id) or not re.fullmatch(r'[A-Z0-9]{6,10}(?:-\d+)?',accession):
        raise ValueError('Use a valid ChEMBL compound ID and UniProt accession.')
    return compound_id,accession

def assessment(prediction, activity, assay, sequence_match):
    reasons=[];value=None;delta=None
    if prediction.dataset!='davis': reasons.append('KIBA and experimental concentration values use different scales.')
    if activity.get('standard_type')!='Kd': reasons.append('Only Kd can be converted to experimental pKd; Ki and IC50 are different endpoints.')
    if activity.get('standard_relation')!='=': reasons.append('Measurement is a bound or has an unspecified relation, not an exact value.')
    units=activity.get('standard_units');factors={'nM':1e-9,'uM':1e-6,'µM':1e-6,'mM':1e-3,'M':1.0}
    try: concentration=float(activity.get('standard_value'))*factors[units]
    except (TypeError,ValueError,KeyError): concentration=None
    if concentration is None or not math.isfinite(concentration) or concentration<=0: reasons.append('No supported positive concentration value.')
    if not sequence_match: reasons.append('Submitted sequence does not exactly match the UniProt reference sequence.')
    if assay.get('confidence_score')!=9: reasons.append('Assay is not assigned directly to a single protein with ChEMBL confidence 9.')
    if activity.get('assay_variant_mutation') or activity.get('assay_variant_accession'): reasons.append('Assay uses a variant; exact construct matching is not established.')
    if activity.get('data_validity_comment') not in (None,'','Manually validated'): reasons.append('ChEMBL flags a data-validity issue.')
    if activity.get('potential_duplicate'): reasons.append('Potential duplicate record; excluded from numerical comparison.')
    if not reasons:
        value=-math.log10(concentration);delta=prediction.score-value
    return dict(numerically_comparable=not reasons,experimental_pkd=value,prediction_minus_experimental_pkd=delta,
                absolute_error_pkd=abs(delta) if delta is not None else None,reasons=reasons)

def compare(prediction, compound_id='', accession=''):
    compound_id,accession=resolve(prediction,compound_id,accession)
    mol=fetch(f'{BASE}/molecule/{compound_id}.json').json()
    raw=(mol.get('molecule_structures') or {}).get('canonical_smiles')
    if not raw or structure(raw)!=structure(prediction.smiles):
        raise HTTPException(422,'ChEMBL structure does not match the saved prediction, including stereochemistry. Comparison stopped.')
    protein=fetch(f'https://rest.uniprot.org/uniprotkb/{accession}.json').json()
    sequence_match=protein.get('sequence',{}).get('value')==prediction.sequence
    targets=fetch(f'{BASE}/target.json',{'target_components__accession':accession,'limit':100}).json()
    target_ids=[t['target_chembl_id'] for t in targets.get('targets',[]) if t.get('target_type')=='SINGLE PROTEIN' and any(c.get('accession')==accession for c in t.get('target_components',[]))]
    if not target_ids:
        return dict(compound_id=compound_id,accession=accession,sequence_match=sequence_match,records=[],total_matching=0,returned=0,truncated=False,message='No single-protein ChEMBL target found for this accession.',retrieved_at=datetime.now(timezone.utc).isoformat(),limitations='No matching target found; this does not establish absence of binding.')
    data=fetch(f'{BASE}/activity.json',{'molecule_chembl_id':compound_id,'target_chembl_id__in':','.join(target_ids),'limit':50}).json()
    activities=data.get('activities',[])
    ids=list(dict.fromkeys(a['assay_chembl_id'] for a in activities))
    def get_assay(id): return id,fetch(f'{BASE}/assay/{id}.json').json()
    with ThreadPoolExecutor(max_workers=4) as pool: assays=dict(pool.map(get_assay,ids))
    records=[]
    for a in activities:
        assay=assays[a['assay_chembl_id']]
        records.append(dict(activity_id=a['activity_id'],endpoint=a.get('standard_type'),relation=a.get('standard_relation'),
            value=a.get('standard_value'),units=a.get('standard_units'),description=a.get('assay_description'),
            assay_id=a['assay_chembl_id'],confidence=assay.get('confidence_score'),confidence_description=assay.get('confidence_description'),
            organism=a.get('target_organism'),document_id=a.get('document_chembl_id'),year=a.get('document_year'),
            source_url=f"{BASE}/activity/{a['activity_id']}.json",assay_url=f"{BASE}/assay/{a['assay_chembl_id']}.json",
            document_url=f"{BASE}/document/{a['document_chembl_id']}.json" if a.get('document_chembl_id') else None,
            **assessment(prediction,a,assay,sequence_match)))
    total=data.get('page_meta',{}).get('total_count',len(records))
    return dict(compound_id=compound_id,accession=accession,structure_match=True,sequence_match=sequence_match,
        retrieved_at=datetime.now(timezone.utc).isoformat(),predicted_score=prediction.score,dataset=prediction.dataset,
        total_matching=total,returned=len(records),truncated=total>len(records),records=records,
        limitations='Reference-sequence matching does not establish the exact experimental construct or assay conditions. Training-data overlap is not screened. This is literature evidence comparison, not independent biological validation. No aggregate accuracy is calculated from selected records.')
