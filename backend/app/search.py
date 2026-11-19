from urllib.parse import quote
import re
import httpx
from fastapi import HTTPException

HEADERS = {'User-Agent': 'DeepDTA-Research/1.0 (scientific research application)'}
def fetch(url, params=None, method='GET', data=None):
    try:
        with httpx.Client(timeout=25, headers=HEADERS, follow_redirects=True) as client:
            r = client.request(method, url, params=params, data=data)
        if r.status_code == 404: raise HTTPException(404, 'No matching database record found.')
        if r.status_code == 429: raise HTTPException(503, 'Scientific database is rate limited. Please retry shortly.')
        r.raise_for_status()
        return r
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'Scientific database is unavailable. Try again or enter the sequence/SMILES manually.') from exc

def drugs(query, kind):
    base = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound'
    properties = 'MolecularFormula,MolecularWeight,ConnectivitySMILES,SMILES,IUPACName,XLogP,TPSA,HBondDonorCount,HBondAcceptorCount'
    if kind == 'formula':
        data = fetch(f'{base}/fastformula/{quote(query, safe="")}/cids/JSON', {'MaxRecords': 10}).json()
        cids = data.get('IdentifierList',{}).get('CID',[])[:10]
        if not cids: return []
        result = fetch(f'{base}/cid/{",".join(map(str,cids))}/property/{properties}/JSON').json()
    elif kind == 'smiles':
        result = fetch(f'{base}/smiles/property/{properties}/JSON', method='POST', data={'smiles':query}).json()
    else:
        if kind not in ['name','cid']: raise HTTPException(422, 'Search type must be name, cid, smiles or formula.')
        if kind == 'cid' and not query.isdigit(): raise HTTPException(422, 'CID must be numeric.')
        result = fetch(f'{base}/{kind}/{quote(query,safe="")}/property/{properties}/JSON').json()
    rows=[]
    for p in result.get('PropertyTable',{}).get('Properties',[])[:10]:
        cid=p['CID']
        rows.append(dict(cid=cid,name=p.get('IUPACName',f'CID {cid}'),smiles=p.get('SMILES') or p.get('ConnectivitySMILES'),
                         formula=p.get('MolecularFormula'),molecular_weight=p.get('MolecularWeight'),
                         xlogp=p.get('XLogP'),tpsa=p.get('TPSA'),hbd=p.get('HBondDonorCount'),hba=p.get('HBondAcceptorCount'),source='PubChem',
                         url=f'https://pubchem.ncbi.nlm.nih.gov/compound/{cid}',image=f'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG'))
    return rows

def proteins(query):
    result=fetch('https://rest.uniprot.org/uniprotkb/search', {'query':query,'format':'json','size':10}).json()
    rows=[]
    for p in result.get('results',[]):
        desc=p.get('proteinDescription',{})
        name=desc.get('recommendedName',{}).get('fullName',{}).get('value')
        if not name: name=next(iter(desc.get('submissionNames',[{}])),{}).get('fullName',{}).get('value','Unnamed protein')
        accession=p['primaryAccession']
        locations=[loc.get('location',{}).get('value') for c in p.get('comments',[]) if c.get('commentType')=='SUBCELLULAR LOCATION' for loc in c.get('subcellularLocations',[])]
        diseases=[d.get('disease',{}).get('description') for c in p.get('comments',[]) if c.get('commentType')=='DISEASE' for d in [c]]
        rows.append(dict(accession=accession,name=name,organism=p.get('organism',{}).get('scientificName'),
                         reviewed=p.get('entryType')=='UniProtKB reviewed (Swiss-Prot)',
                         genes=[g.get('geneName',{}).get('value') for g in p.get('genes',[])],
                         sequence=p.get('sequence',{}).get('value'),length=p.get('sequence',{}).get('length'),
                         function=' '.join(t.get('value','') for c in p.get('comments',[]) if c.get('commentType')=='FUNCTION' for t in c.get('texts',[])),
                         structures=[r['id'] for r in p.get('uniProtKBCrossReferences',[]) if r['database']=='PDB'],
                         locations=[x for x in locations if x][:5],diseases=[x for x in diseases if x][:3],
                         source='UniProt',url=f'https://www.uniprot.org/uniprotkb/{accession}/entry'))
    return rows
