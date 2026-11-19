import csv
import importlib.util
from pathlib import Path

from app import ml


def test_cold_benchmark_is_separate_from_deployed_model():
    info = ml.inspect('kiba')
    assert info['available']
    audit = info['cold_benchmarks']
    assert 'separately trained' in audit['purpose']
    assert info['external_validation']['status'] == 'not_established'
    for name in ('cold_drug', 'cold_protein', 'cold_both'):
        row = audit['results'][name]
        assert row['pairs']['test'] > 0
        assert row['metrics']['rmse'] > 0
        assert row['metrics']['training_mean_baseline_rmse'] > row['metrics']['rmse']
    assert audit['results']['cold_drug']['train_test_drug_overlap'] == 0
    assert audit['results']['cold_protein']['train_test_protein_overlap'] == 0
    assert audit['results']['cold_both']['train_test_drug_overlap'] == 0
    assert audit['results']['cold_both']['train_test_protein_overlap'] == 0


def test_external_audit_reports_coverage_and_never_claims_independence(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / 'scripts/audit_external_davis.py'
    spec = importlib.util.spec_from_file_location('audit_external_davis', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.ml, 'predict', lambda dataset, smiles, sequence: {'score': 6.5})
    source = tmp_path / 'literature.csv'
    with source.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(module.REQUIRED))
        writer.writeheader()
        writer.writerow(dict(smiles='CCO', sequence='ACDE', standard_type='Kd', relation='=', kd_nM='100',
                             activity_id='A1', source_url='https://example.org/A1'))
        writer.writerow(dict(smiles='CCO', sequence='ACDE', standard_type='IC50', relation='=', kd_nM='100',
                             activity_id='A2', source_url='https://example.org/A2'))
        writer.writerow(dict(smiles='CCO', sequence='ACDE', standard_type='Kd', relation='=', kd_nM='100',
                             activity_id='A1', source_url='https://example.org/A1'))
    report = module.audit(source, 'Test fixture, not experimental evidence')
    assert report['independent_validation'] is False
    assert (report['submitted_rows'], report['eligible_rows'], report['excluded_rows']) == (3, 1, 2)
    assert report['metrics_on_eligible_rows']['rmse_pkd'] == 0.5
    assert 'Only exact Kd' in report['records'][1]['excluded_reasons'][0]
    assert 'Duplicate activity ID.' in report['records'][2]['excluded_reasons']
