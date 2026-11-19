from app import main,config
from app.db import SessionLocal,User,Usage
from datetime import datetime,timezone
from sqlalchemy import select
from test_workflows import H,INPUT,run

def test_shared_demo_credentials_open_real_workspace_with_isolated_records(client,monkeypatch):
    monkeypatch.setattr(main,'DEMO_LOGIN_EMAIL','rohith123@gmail.com')
    monkeypatch.setattr(main,'DEMO_LOGIN_PASSWORD','admin@123')
    monkeypatch.setattr(config,'DEMO_LOGIN_EMAIL','rohith123@gmail.com')
    body={'email':'rohith123@gmail.com','password':'admin@123'}
    assert client.post('/api/auth/login',json={**body,'password':'wrong'},headers=H).status_code==401
    assert client.post('/api/auth/register',json={'email':body['email'],'name':'Taken','password':'a-long-password-123'},headers=H).status_code==409
    signed=client.post('/api/auth/login',json=body,headers=H)
    assert signed.status_code==200,signed.text
    assert signed.json()['role']=='demo'
    assert signed.json()['unlimited_credits'] is True
    assert client.get('/api/auth/me').json()['email']==body['email']
    assert client.get('/api/dashboard').json()['limit'] is None
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.email==body['email']))
        db.add(Usage(user_id=account.id,month=datetime.now(timezone.utc).strftime('%Y-%m'),count=1000000))
        db.commit()
    assert run(client,INPUT).status_code==201
    assert client.get('/api/dashboard').json()['unlimited_credits'] is True
    assert len(client.get('/api/predictions').json())==1
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.email==body['email']))
        assert account and account.role=='demo'
        account_id=account.id
    assert client.post('/api/auth/logout',headers=H).status_code==200
    assert client.get('/api/predictions').status_code==401
    again=client.post('/api/auth/login',json=body,headers=H)
    assert again.status_code==200 and again.json()['id']==account_id
    assert len(client.get('/api/predictions').json())==1
    assert client.get('/api/admin/stats').status_code==403
