FINAL DEEPDTA

Extract the entire ZIP before running it. All website assets, models and reference data are included.

WINDOWS: Install 64-bit Python 3.11 with the Python launcher. Double-click start.bat.
Or open Command Prompt in this folder and run: py -3.11 start.py
MAC / LINUX: Install Python 3.11. Run: chmod +x start.sh && ./start.sh
Then open http://127.0.0.1:8000/ and keep the terminal open.
Verify without installation: py -3.11 start.py --check (Windows) or ./start.sh --check.

First launch needs internet to create .venv and install Python dependencies. Node.js is not needed.
Allow several GB of disk space and memory for TensorFlow. Supported dependency wheels are needed
for the operating system and CPU. This release was tested on macOS, not on a physical Windows laptop.
A phone/tablet cannot run this Python backend directly. It can access a separately hosted server.

DEMO LOGIN: rohith123@gmail.com / admin@123 (unlimited credits).
Use these credentials only for demonstration. Change/remove them in backend/.env before public hosting.
A fresh local SQLite database is created under backend/storage. Existing private accounts and history
are not transferred. Live PubChem, UniProt, RCSB and ChEMBL requests require internet.

FOLDER MAP
 backend/app         Python API, inference, authentication, reports and research workflows
 backend/models      Optimized Davis ensemble, legacy Davis reference and deployed KIBA model
 backend/data        KIBA records and example docking structures
 backend/tools       Platform-specific docking executables
 backend/storage     Local database created by the launcher
 backend/migrations  Database version updates
 backend/tests       Regression tests
 backend/training    Training source reference (not executed by the website)
 frontend            Editable interface source and ready-built website
 docs                16-slide PowerPoint, model results, workflow guides and project map

The included docking binaries vary by platform. The app reports availability. Docking support may
require a compatible local AutoDock Vina executable on platforms without a bundled binary.
Payments remain a test integration requiring configured provider keys and price IDs.

The application provides research estimates, not experimental measurements or treatment advice.
Davis MSE and concordance are dataset metrics, not a per-prediction correctness percentage.
See docs/DAVIS_RELEASE_NOTES.md for the repeated-benchmark limitations.
