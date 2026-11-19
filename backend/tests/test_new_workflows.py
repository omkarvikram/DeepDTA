"""End-to-end checks for new bounded screening workflows."""
import io
from openpyxl import Workbook
from app.db import SessionLocal, Plan
from app.compound import canonical
from app import search

H={'X-Research-Client':'web','Origin':'http://testserver'}

def login(client):
    r=client.post('/api/auth/register',json={'name':'New workflow tester','email':'new-workflows@example.org',
             'password':'research-test-password-2026'},headers=H)
    assert r.status_code==201,r.text

def test_batch_limit_and_excel_candidate_ranking(client):
    login(client)
    row='invalid,ACDEFGHIKLMNPQRSTVWY\n'
    for count,expected in [(50,200),(51,422)]:
        r=client.post('/api/batch',files={'file':('batch.csv','smiles,sequence\n'+row*count,'text/csv')},headers=H)
        assert r.status_code==expected,r.text
        if count==50: assert len(r.json())==50
    workbook=Workbook(); sheet=workbook.active
    sheet.append(['smiles','drug_name']);sheet.append(['CCO','Ethanol']);sheet.append(['CC(=O)O','Acetic acid']);sheet.append(['','Missing structure'])
    content=io.BytesIO();workbook.save(content)
    r=client.post('/api/optimisation/file',data={'sequence':'ACDEFGHIKLMNPQRSTVWY','dataset':'davis'},
                  files={'file':('drugs.xlsx',content.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},headers=H)
    assert r.status_code==200,r.text
    rows=r.json()['results']
    assert len(rows)==3 and sum('prediction_id' in row for row in rows)==2
    assert rows[0]['score']>=rows[1]['score']
    assert 'error' in rows[2]
    report=client.post('/api/optimisation/report',json={'ids':[row['prediction_id'] for row in rows if 'prediction_id' in row]},headers=H)
    assert report.status_code==200 and report.content.startswith(b'%PDF-')

def test_public_plan_prices_and_no_unearned_activation(client):
    login(client)
    with SessionLocal() as db:
        db.add_all([Plan(id='plus',monthly_limit=100,description='Plus'),
                    Plan(id='pro',monthly_limit=300,description='Pro'),
                    Plan(id='ultra',monthly_limit=800,description='Ultra')]);db.commit()
    result=client.get('/api/billing/plans').json()['plans']
    assert [(x['id'],x['price_inr'],x['monthly_limit']) for x in result]==[
        ('free',0,25),('plus',599,100),('pro',1299,300),('ultra',2499,800)]
    assert all(not x['checkout_enabled'] for x in result)
    assert client.get('/api/auth/me').json()['plan']=='free'

def test_exact_pubchem_structure_required_for_identity(client,monkeypatch):
    login(client)
    p=client.post('/api/predictions',json={'smiles':'CC(=O)O','sequence':'ACDEFGHIKLMNPQRSTVWY'},headers=H).json()
    class Response:
        def __init__(self,data): self.data=data
        def json(self): return self.data
    def wrong(*args,**kwargs):
        return Response({'PropertyTable':{'Properties':[{'CID':1,'SMILES':'CCO'}]}})
    monkeypatch.setattr(search,'fetch',wrong)
    result=client.get(f"/api/predictions/{p['id']}/compound-identity")
    assert result.status_code==200 and result.json()['matched'] is False
    assert canonical('CC(=O)O')[0]!=canonical('CCO')[0]

def test_vina_bundled_example_runs_and_reports_separate_energy(client):
    login(client)
    example=client.get('/api/docking/example')
    assert example.status_code==200 and example.json()['center']==[15.19,53.903,16.917]
    r=client.post('/api/docking/run',data={'example_input':'true','predict_affinity':'true',
                  'protein_sequence':example.json()['protein_sequence']},headers=H)
    assert r.status_code==200,r.text
    data=r.json()
    assert len(data['scores_kcal_mol'])>=1 and data['best_score_kcal_mol']<0
    assert 'REMARK VINA RESULT' in data['pose_pdbqt']
    assert 'not a measured Kd' in data['warning']
    assert data['affinity_prediction']['dataset']=='kiba'
    assert data['affinity_prediction']['score']>0
    assert 'ATOM' in data['pose_pdb']
