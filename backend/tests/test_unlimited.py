from datetime import datetime, timezone
from app.db import SessionLocal,Usage
from app import config
from test_workflows import register,run

def test_unlimited_bypasses_quota_without_affecting_other_accounts(client,monkeypatch):
 user=register(client).json()
 monkeypatch.setattr(config,'UNLIMITED_CREDIT_USER_IDS',frozenset([user['id']]))
 with SessionLocal() as db:
  db.add(Usage(user_id=user['id'],month=datetime.now(timezone.utc).strftime('%Y-%m'),count=1000000));db.commit()
 assert run(client).status_code==201
 dashboard=client.get('/api/dashboard').json()
 assert dashboard['unlimited_credits'] and dashboard['limit'] is None and dashboard['used']==1000001
 monkeypatch.setattr(config,'UNLIMITED_CREDIT_USER_IDS',frozenset())
 assert run(client).status_code==402
 assert client.get('/api/dashboard').json()['limit']==25
