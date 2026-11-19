"""Portable local launcher copied to Final_DeepDTA/start.py."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / 'backend'
REQUIREMENTS = BACKEND / 'requirements.txt'
VENV = ROOT / '.venv'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_package():
    manifest_path = ROOT / 'package_manifest.json'
    if not manifest_path.is_file():
        raise RuntimeError('package_manifest.json is missing. Extract the complete ZIP again.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for relative_path, expected_hash in manifest['files'].items():
        path = ROOT / relative_path
        if not path.is_file() or sha256(path) != expected_hash:
            raise RuntimeError(f'Missing or changed package file: {relative_path}. Extract the complete ZIP again.')
    print(f"Package verified: {len(manifest['files'])} files, Davis and KIBA models, KIBA reference data, frontend and backend.")


def venv_python():
    return VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def main():
    parser = argparse.ArgumentParser(description='Install dependencies and start DeepDTA Research locally.')
    parser.add_argument('--check', action='store_true', help='Verify the downloaded package without installing anything.')
    args = parser.parse_args()
    verify_package()
    if args.check:
        return
    if sys.version_info[:2] != (3, 11):
        raise SystemExit('Python 3.11 is required. Install it, then rerun start.sh or start.bat.')
    python = venv_python()
    if not python.is_file():
        print('Creating a private Python environment in Final_DeepDTA/.venv ...', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
    marker = VENV / '.deepdta_requirements_sha256'
    requirements_hash = sha256(REQUIREMENTS)
    if not marker.is_file() or marker.read_text().strip() != requirements_hash:
        print('Installing Python dependencies. This first run needs internet access and may take several minutes ...', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(REQUIREMENTS)], check=True)
        marker.write_text(requirements_hash + '\n')
    print('Preparing the local database ...', flush=True)
    subprocess.run([str(python), '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND, check=True)
    print('Open http://127.0.0.1:8000/ in this laptop\'s browser. Press Ctrl+C to stop.', flush=True)
    os.execv(str(python), [str(python), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1', '--no-access-log']) if os.name != 'nt' else subprocess.run(
        [str(python), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1', '--no-access-log'], cwd=BACKEND, check=True)


if __name__ == '__main__':
    try:
        os.chdir(BACKEND)
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        raise SystemExit(f'Could not start DeepDTA: {exc}') from exc
