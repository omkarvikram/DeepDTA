# DeepDTA project walkthrough

1. Start with frontend/src/main.tsx: the researcher enters a SMILES string and a protein sequence.
2. The browser sends a checked request to backend/app/main.py.
3. security.py identifies the session, while db.py records the account and credit usage.
4. ml.py chooses Davis or KIBA. davis_ensemble.py loads frozen Davis members and their saved preprocessing.
5. The server returns a score, scale, model version, input warnings and evaluation metadata.
6. The researcher can request compatible published assay records through experimental.py.
7. reports.py exports the saved prediction and provenance. analysis_reports.py handles the other workflows.
8. advanced.py adds batch screening, mutation comparisons and candidate ranking. docking.py runs the separate structural workflow.
9. models, data, tools and storage all sit inside backend. The interface remains inside frontend.
10. start.py verifies the package, installs dependencies in a local environment, upgrades the database and starts the server.

The presentation in this folder distinguishes the published DeepDTA method, the supplied notebooks, the retraining study, and the website features. KIBA's deployed model and calibration remain unchanged in this Davis release. The improved KIBA study result is a research result, not the currently deployed KIBA checkpoint.
