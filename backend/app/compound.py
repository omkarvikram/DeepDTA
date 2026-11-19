"""Source-backed compound identity and model-ranked analogue search."""
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator, DataStructs
from . import ml, search
from .db import get_db
from .security import current_user

router=APIRouter(prefix='/api')

def canonical(smiles):
    mol=Chem.MolFromSmiles(smiles)
    if mol is None: raise HTTPException(422,'Enter a valid drug SMILES.')
    return Chem.MolToSmiles(mol,isomericSmiles=True),mol

@router.get('/predictions/{prediction_id}/compound-identity')
def identity(prediction_id:str,user=Depends(current_user),db=Depends(get_db)):
    from .main import owned
    p=owned(prediction_id,user,db)
    exact,mol=canonical(p.smiles)
    try:
        properties=search.fetch('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/MolecularFormula,MolecularWeight,SMILES,ConnectivitySMILES/JSON',method='POST',data={'smiles':p.smiles}).json()
        row=properties['PropertyTable']['Properties'][0]
        cid=row['CID']
        found,_=canonical(row.get('SMILES') or row.get('ConnectivitySMILES'))
        if found!=exact:
            return {'matched':False,'reason':'PubChem returned a related structure, but the complete isomeric SMILES did not exactly match the prediction input.'}
        info=search.fetch(f'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/description/JSON').json()
        items=info.get('InformationList',{}).get('Information',[])
        title=next((x['Title'] for x in items if x.get('Title')),f'PubChem CID {cid}')
        description=next((x['Description'] for x in items if x.get('Description') and x.get('DescriptionSourceName')=='ChEBI'),None)
        return {'matched':True,'name':title,'formula':row.get('MolecularFormula'),
                'molecular_weight':row.get('MolecularWeight'),'cid':cid,'description':description[:600] if description else None,
                'source':f'https://pubchem.ncbi.nlm.nih.gov/compound/{cid}',
                'note':'Exact chemical identity and composition from PubChem. An affinity score cannot determine a medicine, approved indication, dose, safety, or treatment choice.'}
    except HTTPException as exc:
        if exc.status_code==404: return {'matched':False,'reason':'No exact PubChem identity was found for this input.'}
        raise

class AnalogueInput(BaseModel):
    smiles:str=Field(min_length=1,max_length=2000)
    sequence:str=Field(min_length=1,max_length=10000)
    dataset:str='kiba'

@router.post('/analogues')
def analogues(body:AnalogueInput,user=Depends(current_user),db=Depends(get_db)):
    from .main import PredictInput, run_prediction
    if body.dataset!='kiba': raise HTTPException(422,'Analogue screening currently uses the KIBA two-input model only.')
    base_smiles,base_mol=canonical(body.smiles)
    sequence=ml.clean_sequence(body.sequence)
    original=run_prediction(PredictInput(smiles=base_smiles,sequence=sequence,dataset='kiba',drug_name='Original input'),user,db)
    response=search.fetch('https://www.ebi.ac.uk/chembl/api/data/similarity/'+quote(base_smiles,safe='')+'/70.json',{'limit':50}).json()
    generator=rdFingerprintGenerator.GetMorganGenerator(radius=2,fpSize=2048)
    original_fp=generator.GetFingerprint(base_mol)
    candidates=[]; seen={base_smiles}
    for row in response.get('molecules',[]):
        raw=(row.get('molecule_structures') or {}).get('canonical_smiles')
        if not raw: continue
        try: smiles,mol=canonical(raw)
        except HTTPException: continue
        if smiles in seen or mol.GetNumAtoms()>100: continue
        # ChEMBL can return salt formulations with apparent 100% similarity;
        # use a local whole-structure fingerprint score for display.
        similarity=DataStructs.TanimotoSimilarity(original_fp,generator.GetFingerprint(mol))
        if similarity<0.70: continue
        seen.add(smiles)
        candidates.append((row,smiles,similarity))
        if len(candidates)==10: break
    results=[]
    for row,smiles,similarity in candidates:
        try:
            p=run_prediction(PredictInput(smiles=smiles,sequence=sequence,dataset='kiba',
                     drug_name=row.get('pref_name') or row['molecule_chembl_id'],
                     protein_name='Analogue target'),user,db)
            results.append({'chembl_id':row['molecule_chembl_id'],'name':row.get('pref_name') or row['molecule_chembl_id'],
                            'smiles':smiles,'formula':(row.get('molecule_properties') or {}).get('full_molformula'),
                            'similarity_percent':round(100*similarity,1),'score':p.score,
                            'delta_score':round(p.score-original.score,4),'prediction_id':p.id,
                            'data_context':p.provenance.get('data_context'),
                            'url':'https://www.ebi.ac.uk/chembl/compound_report_card/'+row['molecule_chembl_id']+'/'})
        except (ValueError,ml.ModelUnavailable,HTTPException) as exc:
            db.rollback()
            results.append({'chembl_id':row['molecule_chembl_id'],'name':row.get('pref_name') or row['molecule_chembl_id'],
                            'smiles':smiles,'similarity_percent':round(100*similarity,1),'error':getattr(exc,'detail',str(exc))})
    results.sort(key=lambda x:x.get('score',float('-inf')),reverse=True)
    return {'original_score':original.score,'original_prediction_id':original.id,'results':results,
            'source':'https://www.ebi.ac.uk/chembl/','screening_model':'KIBA two-input',
            'warning':'These are structurally similar research candidates, ordered by predicted KIBA score. A higher predicted score does not prove a drug is better, active in an assay, safe, effective, or suitable for treatment. KIBA is not pKd. Validate with comparable measured target assays and pharmacology.'}
