import io
from pathlib import Path
import numpy as np
from pypdf import PdfReader
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal,Plan
from app import ml
from app.advanced import mutate
H={'X-Research-Client':'web','Origin':'http://testserver'}
INPUT={'smiles':'CC(=O)O','sequence':'ACDEFGHIKLMNPQRSTVWY','drug_name':'Acetic acid','protein_name':'Synthetic pipeline sequence','dataset':'davis'}
def register(c,email='researcher@example.org'):
    return c.post('/api/auth/register',json={'name':'Test researcher','email':email,'password':'research-test-password-2026'},headers=H)
def run(c,body=None): return c.post('/api/predictions',json=body or INPUT,headers=H)
def test_real_inference_auth_storage_pdf_export_and_isolation(client):
    assert register(client).status_code==201
    p=run(client); assert p.status_code==201,p.text
    data=p.json();id=data['id']
    direct=ml.predict('davis',INPUT['smiles'],INPUT['sequence'])['score']
    assert abs(data['score']-direct)<1e-6
    assert data['model_version'].startswith('davis-sha256:')
    assert len(client.get('/api/predictions').json())==1
    report=client.get(f'/api/predictions/{id}/report')
    assert report.status_code==200 and report.content.startswith(b'%PDF-')
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(report.content)).pages)
    assert id in text and 'KIBA was not run' in text and f'{direct:.6f}' in text
    assert 'No calibrated confidence interval' in text
    (Path(__file__).resolve().parents[2]/'docs/sample-report.pdf').write_bytes(report.content)
    exported=client.post('/api/export',json={'ids':[id]},headers=H)
    assert exported.status_code==200 and INPUT['sequence'] in exported.text
    assert client.post('/api/auth/logout',headers=H).status_code==200
    assert client.get(f'/api/predictions/{id}/report').status_code==401
    assert client.post('/api/auth/login',json={'email':'researcher@example.org','password':'research-test-password-2026'},headers=H).status_code==200
    assert client.get(f'/api/predictions/{id}').status_code==200
    with TestClient(app) as other:
        register(other,'other@example.org')
        assert other.get('/api/predictions').json()==[]
        assert other.get(f'/api/predictions/{id}').status_code==404
        assert other.get(f'/api/predictions/{id}/report').status_code==404
        assert other.delete(f'/api/predictions/{id}',headers=H).status_code==404
        assert other.post('/api/export',json={'ids':[id]},headers=H).status_code==404
    assert client.delete(f'/api/predictions/{id}',headers=H).status_code==200
    assert client.get('/api/dashboard').json()['used']==1

def test_validation_never_truncates_or_fabricates(client):
    register(client)
    for update in [{'smiles':'not a molecule'},{'sequence':'A'*10001},{'sequence':'ACDE12'},{'sequence':'>a\nACDE\n>b\nACDE'}]:
        r=run(client,{**INPUT,**update});assert r.status_code==422,r.text
    assert client.get('/api/predictions').json()==[]
    assert client.get('/api/dashboard').json()['used']==0

def test_notebook_encoding_and_model_metadata():
    d,p,_=ml.encode('CC(=O)O','>test\nACDWXY')
    np.testing.assert_array_equal(d[0,:7],[16,16,2,14,21,3,21])
    np.testing.assert_array_equal(p[0,:6],[1,2,3,19,20,21])
    assert d.shape==(1,100) and p.shape==(1,1000) and not np.any(d[0,7:])
    assert len(ml.inspect('kiba')['inputs'])==2 and ml.inspect('davis')['metrics']['test']['n']==5010

def test_security_and_atomic_credit_limits(client):
    assert client.post('/api/auth/register',json={'name':'A','email':'a@example.org','password':'long-password-here'}).status_code==403
    assert register(client).status_code==201
    assert client.get('/api/admin/stats').status_code==403
    assert run(client).status_code==201
    with SessionLocal() as db:
        plan=db.get(Plan,'free');plan.monthly_limit=2;db.commit()
    r=client.post('/api/engineering',json={'smiles':INPUT['smiles'],'sequence':INPUT['sequence'],'mutations':['A1V']},headers=H)
    assert r.status_code==402 and len(client.get('/api/predictions').json())==1
    assert run(client).status_code==201 and run(client).status_code==402
    assert client.get('/api/dashboard').json()['used']==2
    assert client.post('/api/predictions',json=INPUT,headers={'X-Research-Client':'web','Origin':'https://evil.example'}).status_code==403

def test_batch_engineering_optimisation(client):
    register(client)
    content='smiles,sequence,drug_name\nCC(=O)O,ACDEFGHIKLMNPQRSTVWY,Valid\ninvalid,ACDEFGHIKLMNPQRSTVWY,Unsupported\n'
    r=client.post('/api/batch',files={'file':('test.csv',content,'text/csv')},headers=H)
    assert r.status_code==200 and 'prediction' in r.json()[0] and 'error' in r.json()[1]
    r=client.post('/api/engineering',json={'smiles':INPUT['smiles'],'sequence':INPUT['sequence'],'mutations':['A1V']},headers=H)
    assert r.status_code==200,r.text
    assert r.json()['mutated_sequence'].startswith('V') and r.json()['stability'] is None
    assert len(client.get('/api/predictions').json())==3
    r=client.post('/api/optimisation',json={'sequence':INPUT['sequence'],'candidates':['CCO','c1ccccc1','invalid']},headers=H)
    assert r.status_code==200,r.text
    rows=r.json()['results'];assert 'score' in rows[0]
    assert next(x for x in rows if x['smiles']=='c1ccccc1')['descriptors']['formula']=='C6H6'
    assert 'error' in next(x for x in rows if x['smiles']=='invalid')

def test_mutation_validation():
    import pytest
    for change in ['G1V','A0V','A100V','A1A','A1Z']:
        with pytest.raises(ValueError): mutate('ACDE',[change])
    with pytest.raises(ValueError): mutate('ACDE',['A1V','A1G'])
    assert mutate('ACDE',['A1V'])=='VCDE'

def test_billing_fails_closed(client,monkeypatch):
    register(client);monkeypatch.delenv('STRIPE_SECRET_KEY',raising=False)
    assert client.get('/api/billing/plans').json()['configured'] is False
    assert client.post('/api/billing/checkout',json={'plan':'researcher'},headers=H).status_code==503
    assert client.get('/api/auth/me').json()['plan']=='free'
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_live_fake');monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fake')
    assert client.get('/api/billing/plans').json()['configured'] is False
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_fake')
    assert client.post('/api/billing/webhook',content=b'{}',headers={'stripe-signature':'invalid'}).status_code==400

def test_signed_billing_events_idempotent_and_reconciled(client,monkeypatch):
    import json,time,hmac,hashlib
    from app.db import User,BillingEvent
    from app import billing
    from sqlalchemy import select,func
    register(client)
    with SessionLocal() as db:
        user=db.scalar(select(User));user.stripe_customer='cus_test'
        plan=db.get(Plan,'researcher');plan.price_id='price_test';db.commit()
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_fake')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_test')
    class Sub(dict):
        __getattr__=dict.__getitem__
    subscription=Sub(id='sub_test',customer='cus_test',status='active',items={'data':[{'price':{'id':'price_test'}}]})
    monkeypatch.setattr(billing.stripe.Subscription,'retrieve',lambda _:subscription)
    def send(id,kind='customer.subscription.updated',live=False):
        raw=json.dumps({'id':id,'object':'event','type':kind,'livemode':live,'data':{'object':{'id':'sub_test','object':'subscription'}}}).encode()
        stamp=str(int(time.time()));signature=hmac.new(b'whsec_test',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return client.post('/api/billing/webhook',content=raw,headers={'stripe-signature':f't={stamp},v1={signature}'})
    assert send('evt_1').status_code==200
    assert client.get('/api/auth/me').json()['plan']=='researcher'
    assert send('evt_1').status_code==200
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(BillingEvent))==1
    subscription['status']='canceled'
    assert send('evt_2').status_code==200
    assert client.get('/api/auth/me').json()['plan']=='free'
    assert send('evt_live',live=True).status_code==400

def test_single_use_password_reset_revokes_sessions(client):
    import time
    from app.db import User,ResetToken
    from app.security import digest
    from sqlalchemy import select
    register(client)
    token='test-reset-token-with-enough-entropy-for-fixture'
    with SessionLocal() as db:
        user=db.scalar(select(User));db.add(ResetToken(token_hash=digest(token),user_id=user.id,expires_at=time.time()+100));db.commit()
    body={'token':token,'password':'new-research-password-2026'}
    assert client.post('/api/auth/reset-password',json=body,headers=H).status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/reset-password',json=body,headers=H).status_code==400
    assert client.post('/api/auth/login',json={'email':'researcher@example.org','password':body['password']},headers=H).status_code==200

def test_frozen_migration_roundtrip(tmp_path):
    import os,subprocess,sys
    backend=Path(__file__).resolve().parents[1]
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(tmp_path/'migration.db')}
    for command in [('upgrade','head'),('check',),('downgrade','base'),('upgrade','head')]:
        result=subprocess.run([sys.executable,'-m','alembic',*command],cwd=backend,env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
