import csv
import io
import json
import re
import zipfile
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form, Query
from pydantic import BaseModel, Field, ValidationError
from .db import get_db
from .security import current_user
from . import ml, search

router=APIRouter(prefix='/api')
class EngineeringInput(BaseModel):
    smiles:str=Field(min_length=1,max_length=2000)
    sequence:str=Field(min_length=1,max_length=10000)
    mutations:list[str]=Field(min_length=1,max_length=10)

def mutate(sequence,mutations):
    sequence=ml.clean_sequence(sequence); result=list(sequence); positions=set()
    for mutation in mutations:
        match=re.fullmatch(r'([ACDEFGHIKLMNPQRSTVWY])(\d+)([ACDEFGHIKLMNPQRSTVWY])',mutation.upper().strip())
        if not match: raise ValueError('Use substitutions such as A12V with 1-based residue positions.')
        old,position,new=match.groups(); position=int(position)-1
        if position<0 or position>=len(sequence): raise ValueError(f'Mutation {mutation} is outside the sequence.')
        if position in positions: raise ValueError('Specify only one substitution per position.')
        if sequence[position]!=old: raise ValueError(f'{mutation}: original residue is {sequence[position]}, not {old}.')
        if old==new: raise ValueError('A substitution must change the residue.')
        positions.add(position); result[position]=new
    return ''.join(result)

@router.post('/engineering')
def engineering(body:EngineeringInput,user=Depends(current_user),db=Depends(get_db)):
    from .main import run_predictions,PredictInput
    sequence=ml.clean_sequence(body.sequence); changed=mutate(sequence,body.mutations)
    # Validate both before generating records.
    ml.encode(body.smiles.strip(),sequence); ml.encode(body.smiles.strip(),changed)
    original,candidate=run_predictions([PredictInput(smiles=body.smiles,sequence=sequence,protein_name='Original sequence'),PredictInput(smiles=body.smiles,sequence=changed,protein_name='Mutant: '+', '.join(body.mutations))],user,db)
    return {'original_id':original.id,'mutant_id':candidate.id,'original_score':original.score,'mutant_score':candidate.score,'delta_pkd':candidate.score-original.score,'mutated_sequence':changed,'mutations':body.mutations,'stability':None,'warning':'Exploratory score comparison only. Protein folding, function and structural stability were not evaluated. Both predictions consume credits.'}

@router.get('/engineering/report')
def engineering_report(original_id:str,mutant_id:str,user=Depends(current_user),db=Depends(get_db)):
    from .main import owned
    from .analysis_reports import mutation_pdf
    original,mutant=owned(original_id,user,db),owned(mutant_id,user,db)
    if (original.id==mutant.id or original.dataset!='davis' or mutant.dataset!='davis'
        or original.smiles!=mutant.smiles or original.model_version!=mutant.model_version
        or len(original.sequence)!=len(mutant.sequence)):
        raise HTTPException(422,'Select a saved original/mutant Davis pair with the same compound and model.')
    mutations=[f'{old}{i}{new}' for i,(old,new) in enumerate(zip(original.sequence,mutant.sequence),1) if old!=new]
    if not 1<=len(mutations)<=10:
        raise HTTPException(422,'Saved sequences must differ by 1-10 substitutions.')
    return Response(mutation_pdf(original,mutant,mutations,user),media_type='application/pdf',
                    headers={'Content-Disposition':'attachment; filename="protein-mutation-report.pdf"'})

class OptimiseInput(BaseModel):
    sequence:str=Field(min_length=1,max_length=10000)
    candidates:list[str]=Field(min_length=1,max_length=10)
@router.post('/optimisation')
def optimisation(body:OptimiseInput,user=Depends(current_user),db=Depends(get_db)):
    from .main import run_prediction,PredictInput
    sequence=ml.clean_sequence(body.sequence)
    results=[]
    for i,smiles in enumerate(body.candidates):
        row={'smiles':smiles,'candidate':i+1}
        try:
            row['descriptors']=ml.descriptors(smiles)
            p=run_prediction(PredictInput(smiles=smiles,sequence=sequence,drug_name=f'Candidate {i+1}'),user,db)
            row.update(prediction_id=p.id,score=p.score)
        except (ValueError,ml.ModelUnavailable,HTTPException) as exc:
            db.rollback(); row['error']=getattr(exc,'detail',str(exc))
        results.append(row)
    results.sort(key=lambda x:x.get('score',float('-inf')),reverse=True)
    return {'results':results,'ranking':'Descending predicted Davis pKd only; properties are not combined into an efficacy score.','warning':'Candidate structures are supplied by the researcher, not automatically generated. Affinity and Lipinski indicators do not establish safety, efficacy or bioavailability.'}

class OptimisationReportInput(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=10)

@router.post('/optimisation/report')
def optimisation_report(body:OptimisationReportInput,user=Depends(current_user),db=Depends(get_db)):
    from .main import owned
    from .analysis_reports import optimisation_pdf
    if len(set(body.ids))!=len(body.ids): raise HTTPException(422,'Choose each saved candidate once.')
    records=[owned(identifier,user,db) for identifier in body.ids]
    if (len({p.dataset for p in records})!=1 or len({p.sequence for p in records})!=1
        or len({p.model_version for p in records})!=1):
        raise HTTPException(422,'Candidate report requires saved predictions for one target, dataset and model version.')
    return Response(optimisation_pdf(records,user),media_type='application/pdf',
                    headers={'Content-Disposition':'attachment; filename="drug-optimisation-report.pdf"'})

@router.post('/optimisation/file')
async def optimisation_file(sequence:str=Form(...),dataset:str=Form('kiba'),file:UploadFile=File(...),
                            user=Depends(current_user),db=Depends(get_db)):
    """Screen ten named drug structures against one target from CSV or XLSX."""
    from .main import PredictInput, run_prediction
    from starlette.concurrency import run_in_threadpool
    if dataset not in ('davis','kiba'): raise HTTPException(422,'Choose Davis or KIBA.')
    sequence=ml.clean_sequence(sequence)
    if len(sequence)>10000: raise HTTPException(422,'Sequence is too long.')
    raw=await file.read(1_000_001)
    if len(raw)>1_000_000: raise HTTPException(413,'Candidate file exceeds 1 MB.')
    name=(file.filename or '').lower()
    if name.endswith('.csv'):
        try: rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        except (UnicodeError,csv.Error): raise HTTPException(422,'Upload a UTF-8 CSV.')
    elif name.endswith('.xlsx'):
        from openpyxl import load_workbook
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(i.file_size for i in archive.infolist())>5_000_000:
                    raise HTTPException(413,'Expanded spreadsheet exceeds 5 MB.')
            workbook=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
            values=workbook.active.iter_rows(min_row=1,max_row=12,values_only=True)
            headers=[str(x or '').strip().lower() for x in next(values)]
            rows=[dict(zip(headers,row)) for row in values]
            workbook.close()
        except HTTPException: raise
        except Exception as exc: raise HTTPException(422,'Upload a valid .xlsx spreadsheet.') from exc
    else: raise HTTPException(422,'Upload a .csv or .xlsx file.')
    if not 1<=len(rows)<=10: raise HTTPException(422,'The file must contain 1–10 drug rows.')
    if 'smiles' not in rows[0]: raise HTTPException(422,'A smiles column is required; drug_name is optional.')
    results=[]
    for i,row in enumerate(rows,1):
        smiles=str(row.get('smiles') or '').strip()
        drug_name=str(row.get('drug_name') or f'Candidate {i}').strip()[:200]
        item={'row':i+1,'drug_name':drug_name,'smiles':smiles}
        try:
            item['descriptors']=ml.descriptors(smiles)
            body=PredictInput(smiles=smiles,sequence=sequence,dataset=dataset,drug_name=drug_name,protein_name='Uploaded target')
            p=await run_in_threadpool(run_prediction,body,user,db)
            item.update(prediction_id=p.id,score=p.score)
        except (ValueError,ValidationError,ml.ModelUnavailable,HTTPException) as exc:
            db.rollback(); item['error']=getattr(exc,'detail',str(exc))
        results.append(item)
    results.sort(key=lambda x:x.get('score',float('-inf')),reverse=True)
    return {'dataset':dataset,'results':results,
            'ranking':f'Descending predicted {"pKd" if dataset=="davis" else "KIBA score"}; compare within this model only.',
            'warning':'Research screening only. A predicted rank is not measured binding or proof of a better medicine. Each successful row consumes a prediction credit.'}

def structure_context(pdb_id,metadata):
    """Fetch source-named PDB components; never infer a treatment from coordinates."""
    ids=metadata.get('rcsb_entry_container_identifiers',{})
    proteins=[]
    for entity_id in (ids.get('polymer_entity_ids') or [])[:12]:
        record=search.fetch(f'https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id}/{entity_id}').json()
        proteins.append({'name':record.get('rcsb_polymer_entity',{}).get('pdbx_description')
                        or record.get('entity',{}).get('pdbx_description') or 'Unnamed polymer entity'})
    ligand_ids=ids.get('non_polymer_entity_ids') or []
    ligands=[]
    for entity_id in ligand_ids[:15]:
        entity=search.fetch(f'https://data.rcsb.org/rest/v1/core/nonpolymer_entity/{pdb_id}/{entity_id}').json()
        item=entity.get('pdbx_entity_nonpoly',{})
        comp_id=item.get('comp_id')
        if not comp_id: continue
        chemical=search.fetch(f'https://data.rcsb.org/rest/v1/core/chemcomp/{comp_id}').json().get('chem_comp',{})
        name=item.get('name') or chemical.get('name') or comp_id
        ligand={'id':comp_id,'name':name,'formula':chemical.get('formula'),
                'kind':'Ion' if name.upper().endswith(' ION') else chemical.get('type') or 'Non-polymer component',
                'component_url':f'https://www.rcsb.org/ligand/{comp_id}'}
        annotation={}
        if ligand['kind']!='Ion':
            try:
                annotation=search.fetch(f'https://data.rcsb.org/rest/v1/core/drugbank/{comp_id}').json()
            except HTTPException as exc:
                if exc.status_code not in (404,502,503): raise
        info=annotation.get('drugbank_info',{})
        if info:
            ligand['drug_name']=info.get('name')
            categories=info.get('drug_categories') or []
            ligand['kind']=next((x for x in categories if 'inhibitor' in x.lower()),ligand['kind'])
            indication=re.sub(r'\[[^]]+\]','',info.get('indication') or '')
            first_clause=indication.split(',',1)[0].strip(' .;')
            words=first_clause.split()
            if words:
                ligand['indication']=(first_clause+'.') if len(words)<=24 else (' '.join(words[:18])+'... See the linked record for the full indication.')
            if annotation.get('drugbank_container_identifiers',{}).get('drugbank_id'):
                ligand['drugbank_url']='https://go.drugbank.com/drugs/'+annotation['drugbank_container_identifiers']['drugbank_id']
        ligands.append(ligand)
    return proteins,ligands,len(ligand_ids)>15

def load_structure(pdb_id:str,include_coordinates:bool):
    if not re.fullmatch(r'[1-9][A-Za-z0-9]{3}',pdb_id): raise HTTPException(422,'Enter a four-character PDB ID, for example 1CRN.')
    pdb_id=pdb_id.upper()
    response=search.fetch(f'https://files.rcsb.org/download/{pdb_id}.pdb') if include_coordinates else None
    if response is not None and len(response.content)>10_000_000: raise HTTPException(413,'Structure exceeds the viewer size limit.')
    metadata=search.fetch(f'https://data.rcsb.org/rest/v1/core/entry/{pdb_id}').json()
    proteins,ligands,truncated=structure_context(pdb_id,metadata)
    resolutions=metadata.get('rcsb_entry_info',{}).get('resolution_combined') or []
    result={'id':pdb_id,'source':f'https://www.rcsb.org/structure/{pdb_id}',
            'methods':[m.get('method') for m in metadata.get('exptl',[]) if m.get('method')],
            'title':metadata.get('struct',{}).get('title'),'resolution':resolutions[0] if resolutions else None,
            'proteins':proteins,'ligands':ligands,'ligands_truncated':truncated,
            'warning':'Structure retrieved from RCSB PDB. DeepDTA does not generate docking poses or establish a binding site. Ligands shown are from the deposited structure.'}
    if response is not None: result['pdb']=response.text
    return result

@router.get('/structures/search')
def search_structures(q:str=Query(...,min_length=2,max_length=100),user=Depends(current_user)):
    """Find deposited PDB entries by name, then return source titles for selection."""
    query=q.strip()
    if len(query)<2: raise HTTPException(422,'Enter at least two characters to search PDB.')
    request={'query':{'type':'terminal','service':'full_text','parameters':{'value':query}},
             'return_type':'entry','request_options':{'paginate':{'start':0,'rows':6}}}
    response=search.fetch('https://search.rcsb.org/rcsbsearch/v2/query',
                          {'json':json.dumps(request)})
    if response.status_code==204: return {'query':query,'total':0,'records':[]}
    matches=response.json()
    ids=[hit.get('identifier','').upper() for hit in matches.get('result_set',[])[:6]]
    ids=[pdb_id for pdb_id in ids if re.fullmatch(r'[1-9][A-Z0-9]{3}',pdb_id)]
    if not ids: return {'query':query,'total':matches.get('total_count',0),'records':[]}
    fields='rcsb_id struct { title } exptl { method } rcsb_entry_info { resolution_combined }'
    gql=f'query {{ entries(entry_ids: {json.dumps(ids)}) {{ {fields} }} }}'
    entries=search.fetch('https://data.rcsb.org/graphql',{'query':gql}).json()
    if entries.get('errors'): raise HTTPException(502,'PDB metadata is unavailable. Try the RCSB record directly.')
    metadata_by_id={item['rcsb_id']:item for item in entries.get('data',{}).get('entries',[]) if item}
    records=[]
    for pdb_id in ids:
        metadata=metadata_by_id.get(pdb_id)
        if not metadata: continue
        resolutions=metadata.get('rcsb_entry_info',{}).get('resolution_combined') or []
        records.append({'id':pdb_id,'title':metadata.get('struct',{}).get('title') or 'Untitled PDB entry',
                        'methods':[item.get('method') for item in metadata.get('exptl',[]) if item.get('method')],
                        'resolution':resolutions[0] if resolutions else None,
                        'source':f'https://www.rcsb.org/structure/{pdb_id}',
                        'coordinates':f'https://files.rcsb.org/download/{pdb_id}.cif'})
    return {'query':query,'total':matches.get('total_count',len(records)),'records':records,
            'note':'Search results are deposited structures, not prepared docking receptors or binding predictions.'}

@router.get('/structures/{pdb_id}')
def structure(pdb_id:str,user=Depends(current_user)):
    return load_structure(pdb_id,True)

@router.get('/structures/{pdb_id}/report')
def structure_report(pdb_id:str,user=Depends(current_user)):
    from .analysis_reports import structure_pdf
    data=load_structure(pdb_id,False)
    return Response(structure_pdf(data,user),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="structure-{data["id"]}.pdf"'})
