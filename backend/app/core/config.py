import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / '.env')
DATA_DIR = (ROOT / os.getenv('PFE_DATA_DIR', 'data')).resolve()
OAUTH_FILE = (ROOT / os.getenv('PFE_OAUTH_CLIENT_FILE', 'data/credentials.json')).resolve()
TIMEZONE = os.getenv('PFE_TIMEZONE', 'Africa/Casablanca')
MAX_PDF = 8 * 1024 * 1024
MAX_ATTACHMENTS = 15 * 1024 * 1024
ORIGINS = ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000']
