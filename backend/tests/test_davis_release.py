import io,json
from pathlib import Path
import numpy as np
from pypdf import PdfReader
from app import ml,davis_ensemble

def test_release_matches_frozen_validation_predictions():
    examples=json.loads((davis_ensemble.DIRECTORY/'parity_examples.json').read_text())
    for row in examples:
        result=ml.predict('davis',row['smiles'],row['sequence'])
        assert abs(result['score']-row['expected'])<2e-6
        assert result['provenance']['metrics']['test']['n']==5010
        assert result['provenance']['numerical_accuracy']['status']=='unavailable'

def test_new_vocabulary_and_cropping_are_disclosed():
    result=ml.predict('davis','c1ccccc1','A'*3000)
    assert np.isfinite(result['score'])
    assert result['sequence']=='A'*3000
    assert any('first' in s and '3000' in s for s in result['provenance']['warnings'])

def test_davis_report_records_checkpoint_benchmark(client):
    headers={'X-Research-Client':'web','Origin':'http://testserver'}
    client.post('/api/auth/register',json={'name':'Release check','email':'release@example.org','password':'release-validation-pass'},headers=headers)
    r=client.post('/api/predictions',json={'dataset':'davis','smiles':'CCO','sequence':'ACDEFGHIKLMNPQRSTVWY'},headers=headers)
    assert r.status_code==201,r.text
    pdf=client.get('/api/predictions/'+r.json()['id']+'/report')
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert 'Davis model evaluation' in text
    assert 'Retrospective benchmark' in text
    assert 'concordance index' in text
