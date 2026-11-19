import os,tempfile
from pathlib import Path
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp())/'test.db')
os.environ['APP_URL']='http://testserver'
os.environ['ALLOWED_ORIGINS']='http://testserver'
import pytest
from sqlalchemy import delete
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal,Plan
from app.main import app,requests_by_key
@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables): db.execute(delete(table))
        db.add_all([Plan(id='free',monthly_limit=25,description='Free'),Plan(id='researcher',monthly_limit=1000,description='Researcher'),Plan(id='laboratory',monthly_limit=10000,description='Laboratory')]);db.commit()
    requests_by_key.clear()
    yield
@pytest.fixture
def client():
    with TestClient(app) as c: yield c
