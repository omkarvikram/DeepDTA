# Backend presentation map

All server runtime code and assets live in this folder. The frontend is separate.

| Folder / module | What to explain |
| --- | --- |
| app/main.py | API entry point, request checks, accounts and saved predictions |
| app/ml.py | Shared inference interface and provenance |
| app/davis_ensemble.py | Optimized Davis inference with exact training preprocessing |
| app/kiba_features.py | Versioned two-input KIBA feature extraction |
| app/experimental.py | ChEMBL assay retrieval and compatible endpoint comparison |
| app/search.py, compound.py | PubChem, UniProt and compound information |
| app/advanced.py | Batch screening, mutation scoring and candidate ranking |
| app/docking.py | Structure preparation, search boxes and AutoDock Vina execution |
| app/reports.py, analysis_reports.py | Separate downloadable PDF reports |
| app/db.py, security.py | Database records, password hashing, sessions and credits |
| app/billing.py | Subscription plans and configured Stripe test integration |
| models/ | Weights, vocabularies, versioned feature metadata and evaluation evidence |
| data/ | KIBA reference records and bundled docking example |
| tools/ | Platform-specific docking executables |
| storage/ | Local SQLite database, created on first startup |
| migrations/ | Reproducible database schema updates |
| tests/ | API, scientific-reporting and workflow regression tests |

The development checkout retains links from platform/models, data and tools to these folders so existing research scripts continue to resolve their original paths. The portable release has no dependency on those links. Its top-level folders are backend, frontend and docs.

The original source database remains as a migration backup in the development checkout. The website now defaults to backend/storage/research.db. Never distribute that private database. The release launcher creates a fresh database.
