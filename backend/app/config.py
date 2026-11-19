import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND / '.env')
load_dotenv(ROOT / '.env')
(BACKEND / 'storage').mkdir(exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{BACKEND / "storage/research.db"}')
MODEL_DIR = Path(os.getenv('MODEL_DIR', str(BACKEND / 'models/legacy'))).resolve()
APP_URL = os.getenv('APP_URL', 'http://localhost:8000').rstrip('/')
PRODUCTION = os.getenv('ENVIRONMENT') == 'production'
COOKIE_SECURE = PRODUCTION or os.getenv('COOKIE_SECURE') == 'true'
ALLOWED_ORIGINS = {APP_URL, *os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8000').split(',')}
if PRODUCTION and not APP_URL.startswith('https://'):
    raise RuntimeError('Production requires an HTTPS APP_URL.')

# Account-ID overrides survive subscription changes without granting admin access.
UNLIMITED_CREDIT_USER_IDS = frozenset(x.strip() for x in os.getenv('UNLIMITED_CREDIT_USER_IDS','').split(',') if x.strip())

# Shared demo credentials for the real sign-in form, configured on the server.
DEMO_LOGIN_EMAIL = os.getenv('DEMO_LOGIN_EMAIL','').strip().lower()
DEMO_LOGIN_PASSWORD = os.getenv('DEMO_LOGIN_PASSWORD','')
