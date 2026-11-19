from types import SimpleNamespace
import pytest
from app.experimental import assessment,compare
from test_workflows import register,run,INPUT,H

def test_numeric_comparison_and_rejections():
 p=SimpleNamespace(dataset='davis',score=7.5)
 a=dict(standard_type='Kd',standard_relation='=',standard_value='100',standard_units='nM')
 assay={'confidence_score':9}
 r=assessment(p,a,assay,True)
 assert r['experimental_pkd']==7 and r['absolute_error_pkd']==0.5
 for change in [{'standard_relation':'>'},{'standard_type':'IC50'},{'standard_units':'unknown'},{'standard_value':'nan'},{'standard_value':'0'},{'assay_variant_mutation':'A1V'},{'data_validity_comment':'Outside typical range'},{'potential_duplicate':1}]:
  result=assessment(p,{**a,**change},assay,True)
  assert not result['numerically_comparable'] and result['experimental_pkd'] is None
 assert not assessment(p,a,{'confidence_score':8},True)['numerically_comparable']
 assert not assessment(p,a,assay,False)['numerically_comparable']
 assert not assessment(SimpleNamespace(dataset='kiba',score=11),a,assay,True)['numerically_comparable']

def test_lookup_identity_checks_and_sources(monkeypatch):
 from app import experimental as e
 p=SimpleNamespace(dataset='davis',score=7.5,smiles='CC(=O)O',sequence='ACDE')
 class Response:
  def __init__(self,data): self.data=data
  def json(self): return self.data
 def fetch(url,params=None):
  if '/molecule/' in url: return Response({'molecule_structures':{'canonical_smiles':'CC(=O)O'}})
  if 'uniprot' in url: return Response({'sequence':{'value':'ACDE'}})
  if '/target.' in url: return Response({'targets':[{'target_chembl_id':'CHEMBL1','target_type':'SINGLE PROTEIN','target_components':[{'accession':'O00141'}]}]})
  if '/activity.' in url: return Response({'activities':[dict(activity_id=1,assay_chembl_id='CHEMBL2',standard_type='Kd',standard_relation='=',standard_value='100',standard_units='nM')],'page_meta':{'total_count':1}})
  return Response({'confidence_score':9})
 monkeypatch.setattr(e,'fetch',fetch)
 result=compare(p,'CHEMBL1','O00141')
 assert result['records'][0]['absolute_error_pkd']==0.5
 assert result['records'][0]['source_url'].endswith('/activity/1.json')
 p.smiles='CCC'
 with pytest.raises(Exception) as error: compare(p,'CHEMBL1','O00141')
 assert error.value.status_code==422

def test_evidence_ownership_and_no_credit(client,monkeypatch):
 from app import experimental as e
 register(client);r=run(client).json();id=r['id']
 monkeypatch.setattr(e,'compare',lambda *args:{'records':[],'total_matching':0})
 assert client.post(f'/api/predictions/{id}/experimental',json={},headers=H).status_code==200
 assert client.get('/api/dashboard').json()['used']==1
 client.post('/api/auth/logout',headers=H)
 assert client.post(f'/api/predictions/{id}/experimental',json={},headers=H).status_code==401
 register(client,'second@example.org')
 assert client.post(f'/api/predictions/{id}/experimental',json={},headers=H).status_code==404

def test_evidence_persisted_in_individual_and_combined_reports(client,monkeypatch):
 import io,json
 from pathlib import Path
 from pypdf import PdfReader
 from app import experimental as e
 from app.config import ROOT
 from test_kiba_model import example
 register(client)
 saved=run(client,example()).json();id=saved['id']
 evidence=json.loads((ROOT/'docs/experimental-live-check.json').read_text())
 monkeypatch.setattr(e,'compare',lambda *args:evidence)
 assert client.post(f'/api/predictions/{id}/experimental',json={},headers=H).status_code==200
 assert client.get(f'/api/predictions/{id}').json()['provenance']['experimental_evidence']==evidence
 pdf=client.get(f'/api/predictions/{id}/report').content
 reader=PdfReader(io.BytesIO(pdf));text='\n'.join(p.extract_text() for p in reader.pages)
 assert 'Experimental evidence comparison' in text and 'IC50 > 10000.0 nM' in text
 assert 'No numerical comparison' in text and 'Homologous single protein' in text
 assert evidence['retrieved_at'] in text and '3229275' in text
 links=[str(a.get_object().get('/A',{}).get('/URI','')) for p in reader.pages for a in p.get('/Annots',[])]
 assert evidence['records'][0]['source_url'] in links
 (ROOT/'docs/kiba-experimental-report.pdf').write_bytes(pdf)
 combined=client.post('/api/reports/combined',json={'ids':[id]},headers=H)
 assert 'Experimental evidence comparison' in '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(combined.content)).pages)
 # A failed refresh leaves the last successful snapshot intact.
 def fail(*args): raise ValueError('Temporary failed lookup')
 monkeypatch.setattr(e,'compare',fail)
 assert client.post(f'/api/predictions/{id}/experimental',json={},headers=H).status_code==422
 assert client.get(f'/api/predictions/{id}').json()['provenance']['experimental_evidence']==evidence
 assert client.get('/api/dashboard').json()['used']==1
