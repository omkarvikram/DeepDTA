"""Strength labels are consistent across API and PDF and remain screening guides."""
import io
from pypdf import PdfReader

from app.strength_guide import describe
from test_workflows import register, run


def test_score_band_boundaries():
    assert [(v,describe('davis',v)['label']) for v in [5,5.999,6,6.999,7,8]] == [
        (5,'Weak'),(5.999,'Weak'),(6,'Moderate'),(6.999,'Moderate'),(7,'Strong'),(8,'Strong')]
    assert [(v,describe('kiba',v)['label']) for v in [11.49,11.5,12.1,12.11]] == [
        (11.49,'Weak (relative)'),(11.5,'Moderate (relative)'),
        (12.1,'Moderate (relative)'),(12.11,'Strong (relative)')]
    assert 'not measured Kd' in describe('davis',5)['caution']
    assert 'not Kd' in describe('kiba',12.2)['caution']


def test_saved_prediction_and_report_share_strength_label(client):
    register(client)
    response=run(client)
    assert response.status_code==201,response.text
    prediction=response.json()
    guide=prediction['strength_guide']
    assert guide['label']==describe('davis',prediction['score'])['label']
    saved=client.get('/api/predictions').json()[0]
    assert saved['strength_guide']==guide
    report=client.get(f"/api/predictions/{prediction['id']}/report")
    assert report.status_code==200
    text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(report.content)).pages)
    assert 'Predicted binding strength' in text and guide['label'] in text
