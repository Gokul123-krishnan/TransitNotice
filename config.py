import os
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
INSTANCE_DIR.mkdir(exist_ok=True)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'salem-transit-notice-secret-key-2026-secure')
    DATABASE_PATH = os.environ.get('DATABASE_PATH', str(INSTANCE_DIR / 'transitnotice.db'))
    
    # Timezone strictly set to Asia/Kolkata (IST)
    TIMEZONE_NAME = 'Asia/Kolkata'
    TIMEZONE = ZoneInfo('Asia/Kolkata')
    
    # Scraper & Refresh settings
    SCRAPER_USER_AGENT = 'TransitNotice-Salem/1.0 (Public Salem City Transit Update Tracker; +http://127.0.0.1:5000/about)'
    SCRAPER_REQUEST_TIMEOUT = int(os.environ.get('SCRAPER_TIMEOUT', '10')) # seconds
    SCRAPER_MAX_RETRIES = 3
    SCRAPER_INTERVAL_MINUTES = int(os.environ.get('SCRAPER_INTERVAL_MINUTES', '15'))
    
    # Salem City Boundary Focus
    CITY_NAME = "Salem"
    STATE_NAME = "Tamil Nadu"
    SALEM_KEY_AREAS = [
        "Salem Central Bus Stand (Old Bus Stand)",
        "Salem New Bus Stand (MGR Central)",
        "Salem Junction (Suramangalam)",
        "Hasthampatti",
        "Fairlands",
        "Five Roads (Ainthu Karadu)",
        "Suramangalam",
        "Ammapet",
        "Kondalampatti",
        "Gorimedu",
        "Steel Plant",
        "Omalur Road",
        "Meyyanur",
        "Shevapet",
        "Gugai",
        "Ayothiyapattinam",
        "Kannankurichi",
        "Alagapuram",
        "Jagirammapalayam",
        "Seelanaickenpatti"
    ]
    
    # Default Admin Credentials for local setup
    DEFAULT_ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
    DEFAULT_ADMIN_PASS = os.environ.get('ADMIN_PASS', 'admin123')
