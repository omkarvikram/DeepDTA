import io
import json
from pathlib import Path
import numpy as np
from pypdf import PdfReader
from app import ml, kiba_features
from app.config import ROOT
from test_workflows import register, run, INPUT, H

def example():
    drugs=json.loads((ROOT/'data/kiba/ligands_can.txt').read_text())
    proteins=json.loads((ROOT/'data/kiba/proteins.txt').read_text())
    return dict(smiles=drugs['CHEMBL1087421'],sequence=proteins['O00141'],dataset='kiba',
                drug_name='CHEMBL1087421',protein_name='O00141')

def test_two_input_kiba_inference_storage_report_and_metrics(client):
    register(client)
    body=example()
    result=run(client,body)
    assert result.status_code==201,result.text
    result=result.json()
    a,b,_=kiba_features.encode(body['smiles'],body['sequence'])
    direct=float(ml.kiba_model()([a,b],training=False).numpy()[0,0])
    assert abs(result['score']-direct)<1e-6
    assert len(ml.kiba_model().inputs)==2 and a.shape==b.shape==(1,2048)
    assert abs(direct-11.1)>0.001 # Model inference, not the reference lookup.
    assert result['provenance']['metrics']['test']['n']==19709
    assert result['provenance']['metrics']['test']['mse'] < result['provenance']['metrics']['test']['training_mean_baseline_mse']
    assert result['model_version'].startswith('kiba-sha256:')
    assert client.get('/api/dashboard').json()['used']==1
    report=client.get('/api/predictions/'+result['id']+'/report')
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(report.content)).pages)
    assert 'KIBA score' in text and 'Architecture and held-out evaluation' in text
    assert 'Davis was not run' in text and f'{direct:.6f}' in text
    (ROOT/'docs/kiba-sample-report.pdf').write_bytes(report.content)
    # Loading Davis after KIBA must not attempt to reconfigure the TF runtime.
    assert run(client,INPUT).status_code==201
    exported=client.post('/api/export',json={'ids':[result['id']]},headers=H)
    assert exported.status_code==200 and 'kiba' in exported.text

def test_kiba_features_keep_full_sequences_and_reject_bad_inputs(client):
    register(client)
    assert not np.array_equal(kiba_features.vector('A'*1200,'protein'),kiba_features.vector('A'*1200+'C','protein'))
    body=example()
    for value in ['ACDEX','ACDE123','>first\nACDE\n>second\nACDE','A'*10001]:
        assert run(client,{**body,'sequence':value}).status_code==422
    result=run(client,{**body,'sequence':'A'*4200})
    assert result.status_code==201,result.text
    assert len(result.json()['sequence'])==4200
    assert any('extrapolation' in x for x in result.json()['provenance']['warnings'])
    assert run(client,{**body,'smiles':'not-valid-smiles'}).status_code==422
