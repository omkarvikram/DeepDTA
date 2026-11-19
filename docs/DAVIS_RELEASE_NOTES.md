# Davis release notes

The website now uses extended_cnn_ngram_blend, selected by validation MSE before the new retrospective test calculation. Higher concordance is better. Reducing CI would worsen ranking quality.

| Measure | Retrained CNN control | Previous ensemble | Current release |
| --- | ---: | ---: | ---: |
| MSE (pKd squared) | 0.441181 | 0.398718 | 0.397315 |
| Concordance index | 0.838899 | 0.851872 | 0.852311 |

Validation MSE: 0.263694. Validation concordance: 0.872766.

The extended CNN selected epoch 97 and stopped at epoch 109. The longer-sequence CNN selected epoch 79 and stopped at 91, but did not beat the shorter CNN on validation. The retained n-gram members keep their original checkpoints. No new ML framework was introduced.

The historical 5,010-pair test has already been inspected. These scores are a retrospective benchmark, not an untouched external validation. Training used 17,272 pairs and checkpoint selection used 4,383 validation pairs after exact/cropped pair-overlap purging. Entity overlap remains. The supplied notebooks previously used the historical test as validation. Do not claim superiority to the original paper from this different protocol.

No calibrated per-prediction Davis accuracy percentage is supplied. Group MSE and CI do not establish that a particular score is correct. A fresh compatible Kd dataset, overlap checks, cold/similarity-aware splits and laboratory confirmation remain important next steps. Overfitting is monitored, not guaranteed absent.

Davis runtime preprocessing now uses its saved training vocabulary and the versioned n-gram features. It supports aromatic SMILES and reports unknown tokens and CNN cropping. The selected ensemble's n-gram branches use full strings. Saved older predictions retain their original score and provenance.

KIBA runtime weights and their checkpoint-specific calibration are unchanged. The stronger KIBA ensemble in the original research report is not deployed in this release.

Backend runtime code, models, data, tools and local storage are under backend/. The portable release starts a fresh database. Private source-laptop accounts/history are excluded. Python 3.11 and first-run internet are required. Physical Windows execution has not been tested here.
